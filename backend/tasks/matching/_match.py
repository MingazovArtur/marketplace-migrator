"""Умный поиск спека по тексту и единая точка выбора целевой категории.

Вынесено без изменений из монолита tasks/matching.py (Р20). Имена категорий
берутся из P-3 кэша (_cache.py), а не выгружаются из БД на каждый вызов.
"""

import logging
import re as _re

from services.category_mapper import CategoryMapper
from services.category_service import category_service
from services.platform_utils import detect_platform
from services.template_filler import has_official_template
from tasks.matching._cache import (
    _platform_has_any_specs,
    _spec_cache_load,
    _spec_cache_names,
    _spec_name_exists,
)
from tasks.matching._text import _stem_ru

logger = logging.getLogger(__name__)
category_mapper = CategoryMapper()


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
        logger.warning(
            f"⚠️ Ручной маппинг указывает на '{manual_name}', но её нет в спеках — игнорирую"
        )

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
            or (
                category_name
                if category_name and category_name not in ("Не указана", "—")
                else None
            )
            or auto_name
            or "Товары для дома"
        )
        return fallback_cat, "эталонный шаблон / авто-категория"

    return None, "не найдено"
