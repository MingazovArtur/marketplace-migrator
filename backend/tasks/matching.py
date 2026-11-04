"""
Подбор целевой категории и канонических атрибутов для миграции.

Выделено из монолитного tasks.py (E-5, неделя 4). Содержит:
  - конфигурацию канонических атрибутов XLS-шаблона Ozon;
  - P-3: TTL-кэш справочника спеков площадки (было: своя сессия БД и
    полная выгрузка ВСЕХ имён категорий на каждый вызов);
  - умный поиск спека по тексту (_match_spec_by_text со стеммингом);
  - единую точку определения целевой категории (_pick_target_category);
  - авто-дозаполнение обязательных атрибутов шаблона Ozon.
"""

import logging
import re as _re
import time

from services import defaults_service
from services.category_mapper import CategoryMapper
from services.category_service import category_service
from services.platform_utils import detect_platform
from services.template_filler import has_official_template

logger = logging.getLogger(__name__)
category_mapper = CategoryMapper()

# ---------------------------------------------------------------------------
# Конфигурация канонических атрибутов XLS-шаблона Ozon
# ---------------------------------------------------------------------------
CANON_ATTRS = {
    "brand": {
        "names": ["бренд", "брендводеждеиобуви", "брендодеждыиобуви"],
        "fallback": "NoName",
        "dict_pref": "нет бренда",
    },
    "model": {
        "names": [
            "названиемодели",
            "названиемоделидляобъединенияводнукарточку",
            "объединитьнаоднойкарточке",
            "объединитьводнукарточку",
            "модель",
        ],
        "fallback": None,
        "dict_pref": None,
    },
    "type": {
        "names": ["тип"],
        "fallback": "Футболка",
        "dict_pref": None,
    },
    "marking": {
        "names": ["нуженкодмаркировки", "кодмаркировки", "маркировка"],
        "fallback": "Нет",
        "dict_pref": "нет",
    },
}

TNVED_NAMES = ["тнвэдкодыеаэс", "тнвэд", "кодытнвэд"]


def _norm_name(s):
    """Нормализация имени атрибута: убираем всё кроме букв и цифр, в нижний регистр."""
    return _re.sub(r"[^a-zа-я0-9]", "", (s or "").lower())


def _stem_ru(word: str) -> str:
    """Стемминг русских окончаний для сопоставления единственного и множественного числа."""
    w = (word or "").lower().strip()
    if len(w) <= 3:
        return w
    for suffix in (
        "ами",
        "ями",
        "ев",
        "ов",
        "ей",
        "ам",
        "ям",
        "ах",
        "ях",
        "ую",
        "юю",
        "ые",
        "ие",
        "ой",
        "ий",
        "ый",
    ):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    for suffix in ("а", "я", "ы", "и", "е", "о", "у", "ю", "ь"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _safe_float(value, default: float = 0.0) -> float:
    """Безопасное преобразование в float (строки, Decimal, None → default)."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(f"⚠️ Не удалось преобразовать '{value}' в float → {default}")
        return default


def _base_source(source_value: str) -> str:
    """
    Базовый источник импорта — часть до первой стрелки « → ».
    Защита от накопления «Магнит Маркет (Файл) → Ozon → Ozon → Ozon»
    при повторных миграциях одного и того же товара.
    """
    if not source_value:
        return "неизвестно"
    return str(source_value).split(" → ")[0].strip()


# ---------------------------------------------------------------------------
# P-3 (неделя 3): TTL-кэш справочника спеков площадки.
#
# Проблема из ревью: _match_spec_by_text / _spec_name_exists /
# _load_spec_for_category открывали СВОЮ сессию БД и выгружали ВСЕ имена
# категорий площадки при КАЖДОМ вызове. Пакетная миграция 500 товаров →
# тысячи сессий и полных выгрузок справочника (у Ozon это десятки тысяч строк).
#
# Спеки меняются только через refresh_specs_task — поэтому держим их в памяти
# воркера с TTL 5 минут и сбрасываем после обновления спеков.
# ---------------------------------------------------------------------------

_SPEC_CACHE_TTL = 300.0  # секунд
_spec_cache_names: dict = {}       # platform -> [category_name, ...]
_spec_cache_names_set: dict = {}  # platform -> {нормализованное имя, ...}
_spec_cache_specs: dict = {}      # platform -> {имя -> spec JSON}
_spec_cache_has: dict = {}        # platform -> bool (есть ли хоть один спек)
_spec_cache_ts: dict = {}         # platform -> время загрузки (monotonic)
_SPEC_CACHE_MAX_SPECS = 512       # предохранитель по памяти на площадку


def _spec_cache_invalidate(platform: str = None):
    """Сброс кэша (весь или по одной площадке). Вызывается refresh_specs_task."""
    stores = (
        _spec_cache_names,
        _spec_cache_names_set,
        _spec_cache_specs,
        _spec_cache_has,
        _spec_cache_ts,
    )
    if platform:
        for store in stores:
            store.pop(platform, None)
    else:
        for store in stores:
            store.clear()


def _spec_cache_load(platform: str):
    """Загружает имена категорий площадки ОДНИМ запросом (раз в TTL)."""
    ts = _spec_cache_ts.get(platform)
    if ts is not None and (time.monotonic() - ts) < _SPEC_CACHE_TTL:
        return

    from database.models import PlatformCategorySpec
    from database.session import SessionLocal

    db = SessionLocal()
    try:
        names = [
            n
            for (n,) in db.query(PlatformCategorySpec.category_name)
            .filter(PlatformCategorySpec.platform == platform)
            .all()
        ]
    finally:
        db.close()

    _spec_cache_names[platform] = names
    _spec_cache_names_set[platform] = {str(n).strip() for n in names}
    _spec_cache_specs[platform] = {}
    _spec_cache_has[platform] = bool(names)
    _spec_cache_ts[platform] = time.monotonic()


def _platform_has_any_specs(platform: str) -> bool:
    """Проверяет, загружена ли хотя бы одна спецификация для данной площадки в БД."""
    _spec_cache_load(platform)
    return _spec_cache_has.get(platform, False)


def _spec_name_exists(platform: str, name) -> bool:
    """Существует ли ТОЧНОЕ имя категории в спеках площадки (из кэша, без БД)."""
    if not name:
        return False
    _spec_cache_load(platform)
    return str(name).strip() in _spec_cache_names_set.get(platform, set())


def _match_spec_by_text(text, platform: str):
    """
    Умный поиск спека по тексту товара/категории.
    Ищет ТОЧНОЕ имя из platform_category_specs, где:
      1) ТИП (часть после '/') полностью входит в текст — самый высокий приоритет (score ≥ 120);
      2) Основа слова ТИПА совпадает с основой слова из текста товара («Футболка» <-> «Футболки») (score ≥ 100);
      3) ТИП начинается с введённой подстроки (≥4 символов) — префикс-матчинг (score ≥ 60).

    P-3: имена категорий берутся из in-process кэша (_spec_cache_load),
    а не выгружаются из БД на каждый вызов.
    """
    if not text:
        return None

    low = str(text).lower().strip()
    if not low:
        return None

    _spec_cache_load(platform)

    text_words = [w for w in _re.findall(r"[a-zа-яё0-9]+", low) if len(w) >= 3]
    text_stems = {_stem_ru(w) for w in text_words}

    best, best_score = None, 0
    for name in _spec_cache_names.get(platform, []):
        low_name = name.lower()
        type_part = low_name.split("/")[-1].strip()
        if not type_part or len(type_part) < 3:
            continue
        score = 0
        if type_part in low:
            score = 120 + len(type_part)
        elif len(low) >= 4 and type_part.startswith(low):
            score = 60 + len(type_part)
        else:
            type_words = [w for w in _re.findall(r"[a-zа-яё0-9]+", type_part) if len(w) >= 3]
            type_stems = {_stem_ru(w) for w in type_words}
            common = type_stems & text_stems
            if common:
                score = 100 + 15 * len(common)

        if score > best_score:
            best, best_score = name, score
    return best


def _pick_target_category(product: dict, edited_category, target_platform: str, user_id: int):
    """
    Единая точка определения целевой категории. Возвращает (имя_спека, источник).
    """
    # 1) Категория из модалки
    if edited_category and _spec_name_exists(target_platform, edited_category):
        return str(edited_category).strip(), "модалка"

    # 2) Уже выставленный mapped_category
    existing = product.get("mapped_category")
    if existing and _spec_name_exists(target_platform, existing):
        return existing, "mapped_category"

    # 3) Ручной маппинг
    source_platform = detect_platform(product.get("source"))
    mapping = category_service.get_mapping_for_product(
        source_platform, product.get("category"), target_platform, user_id
    )
    manual_name = (
        mapping.get("target_category_name") if (mapping and mapping.get("is_manual")) else None
    )
    if manual_name:
        if _spec_name_exists(target_platform, manual_name):
            return manual_name, "ручной маппинг"
        logger.warning(f"⚠️ Ручной маппинг указывает на '{manual_name}', но её нет в спеках — игнорирую")

    # 4) Авто-маппинг + проверка
    category_name = product.get("category")
    map_text = (
        category_name
        if category_name and category_name not in ("Не указана", "Без категории", "—")
        else (product.get("name") or "Дом и сад")
    )
    auto_map = category_mapper.auto_map_by_text(map_text, target_platform)
    auto_name = auto_map.get("name") if auto_map else None
    if auto_name and auto_name != "Неизвестно":
        if _spec_name_exists(target_platform, auto_name):
            return auto_name, "авто-маппинг"
        logger.warning(
            f"⚠️ Авто-маппинг нашёл '{auto_name}', но такой категории нет в спеках {target_platform}"
        )

    # 5) Поиск типа товара по спекам
    spec_name = (
        _match_spec_by_text(map_text, target_platform)
        or _match_spec_by_text(product.get("name"), target_platform)
        or category_mapper.auto_map_to_spec(map_text, target_platform)
        or category_mapper.auto_map_to_spec(product.get("name"), target_platform)
    )
    if spec_name:
        return spec_name, "поиск по спекам"

    # 6) Фолбэк для площадок с загруженным эталонным шаблоном (например, Яндекс Маркет)
    #    или площадок, где спеки в БД не загружены:
    has_tpl = has_official_template(edited_category or existing or "", platform=target_platform)
    has_specs_in_db = _platform_has_any_specs(target_platform)
    if has_tpl or not has_specs_in_db or target_platform != "ozon":
        fallback_cat = (
            (str(edited_category).strip() if edited_category else None)
            or manual_name
            or (existing if existing and existing not in ("Не указана", "—") else None)
            or (category_name if category_name and category_name not in ("Не указана", "—") else None)
            or auto_name
            or "Товары для дома"
        )
        return fallback_cat, "эталонный шаблон / авто-категория"

    return None, "не найдено"


def _load_spec_for_category(target_platform: str, category_name: str):
    """Загружает спек из БД по имени категории (P-3: с кэшем по имени). Возвращает JSON-dict или None."""
    if not category_name:
        return None

    _spec_cache_load(target_platform)
    key = str(category_name).strip()
    cache = _spec_cache_specs.setdefault(target_platform, {})
    if key in cache:
        return cache[key]

    from database.models import PlatformCategorySpec
    from database.session import SessionLocal

    db = SessionLocal()
    try:
        row = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == target_platform,
                PlatformCategorySpec.category_name == category_name,
            )
            .first()
        )
        spec = row.spec if row else None
    finally:
        db.close()

    # предохранитель по памяти: не копим безлимитный кэш JSON-спеков
    if len(cache) >= _SPEC_CACHE_MAX_SPECS:
        cache.clear()
    cache[key] = spec
    return spec


def _ensure_canonical_attributes(
    product_id: int,
    target_platform: str,
    target_category_name: str,
    product_name: str,
    okpd_code: str = None,
    user_id: int = None,
):
    if target_platform != "ozon" or not target_category_name:
        return

    spec = _load_spec_for_category(target_platform, target_category_name)
    if not spec or not isinstance(spec, dict):
        return

    defaults = (
        defaults_service.get_merged_defaults(user_id, target_category_name) if user_id else {}
    )
    spec_attrs = {
        _norm_name(a.get("name")): a for a in (spec.get("attributes") or []) if a.get("name")
    }
    if not spec_attrs:
        return

    derived_type = defaults_service.derive_type_value(target_category_name, spec)

    from database.models import ProductAttribute
    from database.session import SessionLocal

    db = SessionLocal()
    try:
        existing = {
            _norm_name(a.name)
            for a in db.query(ProductAttribute)
            .filter(ProductAttribute.product_id == product_id)
            .all()
        }
        added = 0
        for canon, cfg in CANON_ATTRS.items():
            keys = [n for n in cfg["names"] if n in spec_attrs and n not in existing]
            if not keys:
                continue

            first_attr = spec_attrs[keys[0]]
            values = first_attr.get("values") or []

            if canon == "model":
                value = (product_name or "").strip()[:50] or "Модель"
            elif canon == "type" and derived_type:
                value = derived_type
            elif canon == "brand":
                pref = (defaults.get("brand") or "").strip().lower()
                value = (
                    next((v for v in values if pref and pref in str(v).lower()), None)
                    or next((v for v in values if "нет бренда" in str(v).lower()), None)
                    or (values[0] if values else cfg["fallback"])
                )
            elif canon == "marking":
                value = defaults.get("marking") or next(
                    (v for v in values if str(v).lower() == "нет"), "Нет"
                )
            elif cfg.get("dict_pref") and values:
                value = next((v for v in values if cfg["dict_pref"] in str(v).lower()), values[0])
            elif values:
                value = values[0]
            else:
                value = cfg.get("fallback")
            if value is None:
                continue

            for key in keys:
                db.add(
                    ProductAttribute(
                        product_id=product_id,
                        name=spec_attrs[key].get("name"),
                        value=str(value),
                        sort_order=0,
                    )
                )
                existing.add(key)
                added += 1

        # ТН ВЭД из карточки или дефолтов
        okpd = okpd_code or defaults.get("okpd_code")
        tnved_key = next((n for n in TNVED_NAMES if n in spec_attrs and n not in existing), None)
        if okpd and tnved_key:
            db.add(
                ProductAttribute(
                    product_id=product_id,
                    name=spec_attrs[tnved_key].get("name"),
                    value=str(okpd),
                    sort_order=0,
                )
            )
            added += 1

        db.commit()
        if added:
            logger.info(
                f"🧩 Товар {product_id}: авто-добавлено {added} обязательных атрибутов шаблона"
            )
    except Exception as e:
        db.rollback()
        logger.warning(f"Авто-атрибуты для товара {product_id} не записаны: {e}")
    finally:
        db.close()
