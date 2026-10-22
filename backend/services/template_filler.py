"""
Мультиплатформенное хранилище и заполнение ЭТАЛОННЫХ шаблонов площадок
(Ozon, Яндекс Маркет, Wildberries, Магнит Маркет, Мегамаркет,
Холодильник.ру, AliExpress).

Пользователь скачивает официальный XLSX-шаблон в кабинете площадки и загружает
его в разделе «Шаблоны». При выгрузке мы открываем этот файл как КАРКАС:
все листы («Инструкция», «Список товаров», «Шаблон», скрытые словари), шапка,
стили, выпадающие списки и метаданные остаются 100% оригинальными — мы только
удаляем строку-пример и записываем товары в соответствующие столбцы.

✅ Если для площадки загружен хотя бы один шаблон (например, «Универсальный»),
   он автоматически используется для выгрузки всех товаров на эту площадку.
"""

import io
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(os.getenv("OZON_TEMPLATES_DIR", "/app/templates/ozon"))
INDEX_PATH = TEMPLATES_DIR / "index.json"

VAT_LABELS = {"none": "Не облагается", "22": "22", "10": "10", "7": "7", "5": "5"}

BRAND_SYNONYMS = ["бренд", "брендводеждеиобуви", "брендодеждыиобуви", "производитель", "brand"]
MODEL_SYNONYMS = [
    "объединитьнаоднойкарточке",
    "названиемодели",
    "названиемоделидляобъединенияводнукарточку",
    "модель",
    "модельsellerspuid",
    "sellerspuid",
]
MARKING_SYNONYMS = ["нуженкодмаркировки", "кодмаркировки", "маркировка"]

UNIVERSAL_NAMES = {
    "универсальный",
    "универсальный (все категории)",
    "общий",
    "все категории",
    "default",
    "all",
}


# ==================== Служебные функции ====================


def _norm(s: str) -> str:
    """Нормализация имени колонки/атрибута: только буквы+цифры, нижний регистр."""
    return re.sub(r"[^a-zа-я0-9]", "", (s or "").lower())


def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Zа-яА-Я]+", "_", name).strip("_")[:80] or "template"


def _normalize_multi(value: str) -> str:
    """Формат множественного выбора: «a;b» без лишних пробелов."""
    parts = re.split(r"[;,]", value or "")
    return ";".join(p.strip() for p in parts if p.strip())


def _strip_html(text: str) -> str:
    """Очищает описание от HTML-тегов (<p>, <br> и т.д.)."""
    if not text:
        return ""
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", str(text))
    cleaned = re.sub(r"(?i)</p>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">")):
        cleaned = cleaned.replace(ent, ch)
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def _generate_ean13(product: dict, prefix: str = "460") -> str:
    """
    Генерирует валидный 13-значный штрихкод GTIN / EAN-13 по стандарту GS1.
    Префикс 460 подходит для всех российских маркетплейсов (включая Мегамаркет,
    который отклоняет штрихкоды, начинающиеся с 2).
    """
    pid = int(product.get("id") or 1)
    base12 = f"{prefix}{pid:09d}"[:12]
    odd_sum = sum(int(base12[i]) for i in range(0, 12, 2))
    even_sum = sum(int(base12[i]) for i in range(1, 12, 2))
    check_digit = (10 - ((odd_sum + even_sum * 3) % 10)) % 10
    return f"{base12}{check_digit}"


def _format_comma_decimal(val: float | int | None) -> str | None:
    """Форматирует число с запятой и максимум 2 знаками после запятой (правило Мегамаркета)."""
    if val is None:
        return None
    try:
        num = round(float(val), 2)
        if num <= 0:
            return None
        s = f"{num:.2f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")
    except (TypeError, ValueError):
        return None


def _guess_category(product: dict) -> str:
    """Возвращает чистое название категории без значения «Не указана»."""
    for field in ("mapped_category", "category"):
        raw = (product.get(field) or "").strip()
        if raw and raw.lower() not in ("не указана", "без категории", "не маппировалось", "—"):
            parts = [p.strip() for p in re.split(r"[/\\>]", raw) if p.strip()]
            return parts[-1] if parts else raw

    name_low = (product.get("name") or "").lower()
    rules = [
        (["футболк", "майк", "лонгслив"], "Футболки и майки"),
        (["плать", "сарафан"], "Платья и сарафаны"),
        (["брюк", "джинс", "штаны"], "Брюки"),
        (["куртк", "пуховик", "ветровк", "пальто"], "Верхняя одежда"),
        (["толстовк", "худи", "свитшот", "джемпер", "свитер"], "Толстовки, свитшот и худи"),
        (["носки", "гольф", "колготк"], "Носки, чулки и колготки"),
        (["кроссовк", "кеды"], "Кроссовки и кеды"),
        (["смартфон", "телефон"], "Мобильные телефоны"),
        (["наушник", "гарнитур"], "Наушники и Bluetooth-гарнитуры"),
        (["швабр", "ведро", "щетк"], "Инвентарь для уборки"),
    ]
    for keywords, cat in rules:
        if any(k in name_low for k in keywords):
            return cat
    return "Товары для дома"


def _make_key(platform: str, category_name: str) -> str:
    return f"{(platform or 'ozon').lower().strip()}::{(category_name or '').strip()}"


def _parse_key(raw_key: str, meta: dict) -> tuple[str, str]:
    if "::" in raw_key:
        pl, cat = raw_key.split("::", 1)
        return pl.lower().strip(), cat.strip()
    pl = (meta.get("platform") or "ozon").lower().strip()
    return pl, raw_key.strip()


def _load_index() -> dict[str, dict]:
    """Читает index.json с поддержкой мультиплатформенности и обратной совместимости."""
    if not INDEX_PATH.exists():
        return {}
    try:
        raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for k, val in (raw or {}).items():
        if isinstance(val, str):
            pl, cat = _parse_key(k, {})
            norm_key = _make_key(pl, cat)
            out[norm_key] = {
                "platform": pl,
                "category_name": cat,
                "file": val,
                "uploaded_at": None,
                "uploaded_by": None,
                "columns": None,
            }
        elif isinstance(val, dict) and val.get("file"):
            pl, cat = _parse_key(k, val)
            cat_name = val.get("category_name") or cat
            norm_key = _make_key(pl, cat_name)
            out[norm_key] = {
                "platform": pl,
                "category_name": cat_name,
                "file": val.get("file"),
                "uploaded_at": val.get("uploaded_at"),
                "uploaded_by": val.get("uploaded_by"),
                "columns": val.get("columns"),
            }
    return out


def _save_index(index: dict[str, dict]) -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_data_sheet(wb):
    """Находит рабочий лист с товарами в книге любой площадки."""
    for candidate in (
        "Список товаров",
        "Шаблон",
        "Товары",
        "Офферы",
        "Шаблон Поставщика",
        "Assortment",
        "Каталог",
    ):
        if candidate in wb.sheetnames:
            return wb[candidate]
    skip_words = (
        "инструкция",
        "описание полей",
        "справочник",
        "видео",
        "документация",
        "правила",
        "требования к изображениям",
        "readme",
        "help",
    )
    for name in wb.sheetnames:
        if not any(w in name.lower() for w in skip_words):
            return wb[name]
    return wb.active


def _find_header_row(ws) -> int | None:
    """
    Ищет строку заголовков по ключевым колонкам площадок:
    - Ozon / WB / Магнит / Холодильник: «Артикул», «Ваш SKU *», «Артикул продавца»
    - Мегамаркет: «Код товара продавца», «Основной штрихкод (GTIN)»
    - AliExpress: «Модель (seller SPU ID)*», «Артикул/Штрихкод (seller SKU ID)*»
    """
    header_markers = {
        "артикул",
        "вашsku",
        "артикулпродавца",
        "артикулsku",
        "кодтоварапродавца",
        "кодтоварапродавцаofferid",
        "основнойштрихкодgtin",
        "модельsellerspuid",
        "артикулштрихкодsellerskuid",
        "sellerskuid",
        "sellerspuid",
        "offerid",
        "sku",
        "наименование",
        "наименованиетовара",
        "названиетовара",
    }
    for row in range(1, 12):
        for cell in ws[row]:
            if cell.value:
                norm_val = _norm(str(cell.value).rstrip("*"))
                if norm_val in header_markers:
                    return row
    return None


def _detect_data_start_row(ws, header_row: int, platform: str) -> int:
    """
    Определяет строку, с которой начинаются данные товаров:
    - AliExpress: строка 1 — блоки, строка 2 — подсказки, строка 3 — заголовки (`header_row = 3`),
      данные начинаются со строки 4 (`header_row + 1`).
    - Мегамаркет: если заголовки в 1-й строке — данные со 2-й строки (`header_row + 1`).
    - Яндекс Маркет: строка 2 — заголовки, строка 3 — подсказки, строка 4 — данные (`header_row + 2`).
    - Ozon: строка 2 — заголовки, строка 3 — «Обязательное поле», строка 4 — подсказки, строка 5 — данные (`header_row + 3`).
    """
    if platform == "aliexpress":
        return header_row + 1

    if platform == "yandex":
        return header_row + 2

    row_plus_1_text = " ".join(
        str(c.value).lower() for c in ws[header_row + 1] if c.value is not None
    )
    if "обязательное поле" in row_plus_1_text or "рекомендуем к заполнению" in row_plus_1_text:
        return header_row + 3

    if any(
        m in row_plus_1_text
        for m in (
            "уникальный идентификатор",
            "значение поля выгружено",
            "заполняется автоматически",
            "обязательный параметр",
            "необязательный параметр",
            "уникальный код товара",
        )
    ):
        return header_row + 2

    if platform == "megamarket":
        return header_row + 1

    return header_row + 1 if header_row in (1, 3) else 5


def _count_columns(data: bytes) -> int | None:
    """Число непустых колонок в строке заголовков шаблона."""
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True)
        try:
            ws = _find_data_sheet(wb)
            row = _find_header_row(ws) or 2
            return sum(1 for c in ws[row] if c.value not in (None, ""))
        finally:
            wb.close()
    except Exception:
        return None


# ==================== Поиск эталона с умным фолбэком ====================


def _resolve_template_meta(category_name: str | None, platform: str = "ozon") -> dict | None:
    """
    Ищет подходящий эталонный шаблон для площадки:
      1. Точное совпадение (platform, category_name).
      2. Совпадение по конечному типу категории («Одежда / Футболки» -> «Футболки»).
      3. Универсальный шаблон площадки («Универсальный», «Общий», «Все категории»).
      4. Фолбэк: первый доступный шаблон этой площадки.
    """
    pl = (platform or "ozon").lower().strip()
    cat = (category_name or "").strip()
    idx = _load_index()

    platform_templates: list[dict] = []
    for meta in idx.values():
        if meta.get("platform") == pl and (TEMPLATES_DIR / meta["file"]).exists():
            platform_templates.append(meta)

    if not platform_templates:
        return None

    if cat:
        for m in platform_templates:
            if m["category_name"].lower() == cat.lower():
                return m

        cat_leaf = cat.split("/")[-1].strip().lower()
        for m in platform_templates:
            m_leaf = m["category_name"].split("/")[-1].strip().lower()
            if cat_leaf and m_leaf == cat_leaf:
                return m

    for m in platform_templates:
        if m["category_name"].strip().lower() in UNIVERSAL_NAMES:
            return m

    return platform_templates[0]


# ==================== Публичный API хранилища ====================


def has_official_template(category_name: str = "", platform: str = "ozon") -> bool:
    return _resolve_template_meta(category_name, platform) is not None


def template_path(category_name: str = "", platform: str = "ozon") -> Path | None:
    meta = _resolve_template_meta(category_name, platform)
    if not meta:
        return None
    p = TEMPLATES_DIR / meta["file"]
    return p if p.exists() else None


def get_template_meta(category_name: str = "", platform: str = "ozon") -> dict | None:
    return _resolve_template_meta(category_name, platform)


def list_official_templates(platform: str | None = None) -> list[dict]:
    """Метаданные всех эталонов (опционально отфильтрованные по площадке)."""
    idx = _load_index()
    res = []
    pl_filter = platform.lower().strip() if platform else None
    for meta in idx.values():
        if pl_filter and meta.get("platform") != pl_filter:
            continue
        if (TEMPLATES_DIR / meta["file"]).exists():
            res.append(meta)
    return sorted(res, key=lambda x: (x.get("platform") or "ozon", x.get("category_name") or ""))


def list_template_names(platform: str | None = None) -> list[str]:
    return [t["category_name"] for t in list_official_templates(platform=platform)]


def read_template_bytes(category_name: str, platform: str = "ozon") -> bytes | None:
    idx = _load_index()
    exact = idx.get(_make_key(platform, category_name))
    if exact and (TEMPLATES_DIR / exact["file"]).exists():
        return (TEMPLATES_DIR / exact["file"]).read_bytes()
    p = template_path(category_name, platform=platform)
    return p.read_bytes() if p else None


def save_official_template(
    category_name: str,
    data: bytes,
    uploaded_by: str | None = None,
    platform: str = "ozon",
) -> dict:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    pl = (platform or "ozon").lower().strip()
    cat = (category_name or "").strip() or "Универсальный (все категории)"

    idx = _load_index()
    key = _make_key(pl, cat)
    fname = f"{pl}_{_slug(cat)}.xlsx"

    owner = next((k for k, m in idx.items() if m["file"] == fname), None)
    if owner and owner != key:
        fname = f"{pl}_{_slug(cat)}_{abs(hash(key)) % 10000}.xlsx"

    (TEMPLATES_DIR / fname).write_bytes(data)
    meta = {
        "platform": pl,
        "category_name": cat,
        "file": fname,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "uploaded_by": uploaded_by,
        "columns": _count_columns(data),
    }
    idx[key] = meta
    _save_index(idx)
    logger.info(
        f"💾 Эталон [{pl}] сохранён: '{cat}' → {fname} "
        f"(колонок: {meta['columns']}, загрузил: {uploaded_by})"
    )
    return meta


def delete_official_template(category_name: str, platform: str = "ozon") -> bool:
    idx = _load_index()
    key = _make_key(platform, category_name)
    meta = idx.pop(key, None)
    if not meta:
        for k in list(idx.keys()):
            if k.lower() == key.lower():
                meta = idx.pop(k)
                break
    _save_index(idx)
    if meta and (TEMPLATES_DIR / meta["file"]).exists():
        (TEMPLATES_DIR / meta["file"]).unlink()
        return True
    return False


def validate_template_bytes(data: bytes, platform: str = "ozon") -> str | None:
    """Проверяет, что загруженный файл является корректным XLSX-шаблоном площадки."""
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True)
    except Exception as e:
        return f"Файл не читается как XLSX: {e}"
    try:
        ws = _find_data_sheet(wb)
        header_row = _find_header_row(ws)
        if header_row is None:
            return (
                "В файле не найдена строка заголовков (ожидается колонка «Артикул», "
                "«Ваш SKU *», «Код товара продавца», «Модель (seller SPU ID)*» или «Наименование»)"
            )
        return None
    finally:
        wb.close()


# ==================== Значения строки товара (Все 7 площадок) ====================


def _row_values(
    product: dict,
    row_num: int,
    enum_fix: dict[str, dict[str, str]],
    platform: str = "ozon",
) -> dict[str, object]:
    """
    Формирует словарь значений строки товара для любой из 7 поддерживаемых площадок:
    Ozon, Wildberries, Яндекс Маркет, Магнит Маркет, Мегамаркет, Холодильник.ру, AliExpress.
    """
    photos = [str(u).strip() for u in (product.get("photos") or []) if str(u).strip()]
    attr_map = {
        _norm(a.get("name")): a.get("value")
        for a in (product.get("attributes") or [])
        if a.get("name")
    }

    raw_article = (
        product.get("_article")
        or product.get("sku")
        or product.get("external_id")
        or f"ID{product.get('id')}"
    )
    if platform == "megamarket":
        # В Мегамаркете запрещены символы # и % в Коде товара продавца
        article = re.sub(r"[#%]+", "_", str(raw_article)).strip()
    elif platform == "aliexpress":
        # В AliExpress Артикул (seller SKU ID) — не более 50 символов
        article = str(raw_article).strip()[:50]
    else:
        article = str(raw_article).strip()

    spu_id = str(product.get("_spu_id") or article)[:50]
    clean_desc = _strip_html(product.get("description") or "") or product.get("name")

    # Бренд
    raw_brand = (
        product.get("brand")
        or attr_map.get("бренд")
        or attr_map.get("брендводеждеиобуви")
        or ""
    ).strip()
    if not raw_brand or raw_brand.lower() in (
        "отсутствует бренд",
        "без бренда",
        "нет бренда",
        "noname",
        "no name",
    ):
        if platform == "aliexpress":
            brand_val = "NONE"
        elif platform == "megamarket":
            brand_val = "Без бренда"
        else:
            brand_val = "Нет бренда"
    else:
        brand_val = raw_brand

    # Штрихкоды (для Мегамаркета основной штрихкод GTIN не может начинаться с 2)
    raw_bc = product.get("barcode") or attr_map.get("штрихкод") or ""
    bc_parts = [p.strip() for p in re.split(r"[;,]", str(raw_bc)) if p.strip()]
    if not bc_parts and platform in (
        "yandex",
        "wildberries",
        "megamarket",
        "holodilnik",
        "aliexpress",
    ):
        for v in product.get("variants") or []:
            v_sku = str(v.get("sku") or "").strip()
            if v_sku.isdigit() and 8 <= len(v_sku) <= 14:
                bc_parts = [v_sku]
                break
        if not bc_parts:
            bc_parts = [_generate_ean13(product, prefix="460")]

    if platform == "megamarket" and bc_parts and bc_parts[0].startswith("2"):
        bc_parts[0] = _generate_ean13(product, prefix="460")

    barcode_semi = ";".join(bc_parts) if bc_parts else None
    barcode_comma = ", ".join(bc_parts) if bc_parts else None
    main_gtin = bc_parts[0] if bc_parts else _generate_ean13(product, prefix="460")

    # Вес и габариты (в граммах/мм и в кг/см)
    wg = product.get("package_weight_grams") or product.get("weight_grams")
    l_mm = product.get("package_length_mm")
    w_mm = product.get("package_width_mm")
    h_mm = product.get("package_height_mm")

    # Для AliExpress и Мегамаркета вес и габариты не могут быть равны 0
    if platform in ("aliexpress", "megamarket"):
        wg = wg or 500
        l_mm = l_mm or 200
        w_mm = w_mm or 150
        h_mm = h_mm or 100

    weight_kg = round(float(wg) / 1000.0, 2) if wg else None
    length_cm = round(float(l_mm) / 10.0, 2) if l_mm else None
    width_cm = round(float(w_mm) / 10.0, 2) if w_mm else None
    height_cm = round(float(h_mm) / 10.0, 2) if h_mm else None
    dims_slash_cm = (
        f"{length_cm}/{width_cm}/{height_cm}"
        if (length_cm and width_cm and height_cm)
        else None
    )

    okpd = product.get("okpd_code") or attr_map.get("тнвэдкодыеаэс") or attr_map.get("тнвэд")
    units = product.get("units_per_item")
    stock_val = product.get("stock") if product.get("stock") is not None else 10
    cat_val = _guess_category(product)
    vat_val = VAT_LABELS.get(
        str(product.get("vat_rate") or ""), product.get("vat_rate") or "Не облагается"
    )

    # Вариационные поля (Цвет / Размер для AliExpress и мультикарточек)
    var_color = (
        product.get("_variant_color")
        or attr_map.get("цвет")
        or attr_map.get("цветтовара")
        or "Разноцветный"
    )
    var_size = (
        product.get("_variant_size")
        or attr_map.get("размер")
        or attr_map.get("размеродежды")
        or ""
    )

    # Сборка колонки «Характеристики товара» для Яндекс Маркета (Имя|Значение;Имя|Значение)
    skip_ym_attrs = {
        "бренд",
        "брендводеждеиобуви",
        "странапроизводства",
        "странаизготовитель",
        "нуженкодмаркировки",
        "маркировка",
        "тнвэдкодыеаэс",
        "тнвэд",
        "названиемодели",
        "названиемоделидляобъединенияводнукарточку",
        "объединитьнаоднойкарточке",
        "модель",
        "тип",
    }
    ym_pairs = []
    for a in product.get("attributes") or []:
        aname = (a.get("name") or "").strip()
        aval = (a.get("value") or "").strip()
        if aname and aval and _norm(aname) not in skip_ym_attrs:
            ym_pairs.append(f"{aname}|{aval}")
    ym_characteristics = ";".join(ym_pairs) if ym_pairs else None

    values: dict[str, object] = {
        # --- Общие и Ozon ---
        "№": row_num,
        "артикул": article,
        "артикулпродавца": article,
        "артикулsku": article,
        "вашsku": article,
        "offerid": article,
        "названиетовара": product.get("name"),
        "название": product.get("name"),
        "наименование": product.get("name"),
        "наименованиетовара": product.get("name"),
        "предельнаяценабезакцийруб": product.get("price"),
        "зачёркнутаяценаруб": product.get("strike_price"),
        "зачеркнутаяценаруб": product.get("strike_price"),
        "ндс": vat_val,
        "штрихкодсерийныйномерean": barcode_semi,
        "штрихкодbarcode": barcode_semi,
        "штрихкодean13": main_gtin,
        "barcode": barcode_semi,
        "тнвэдкодыеаэс": okpd,
        "весвупаковкег": wg,
        "ширинаупаковкимм": w_mm,
        "высотаупаковкимм": h_mm,
        "длинаупаковкимм": l_mm,
        "ссылканаглавноефото": photos[0] if photos else None,
        "ссылкинадополнительныефото": " ".join(photos[1:15]) if len(photos) > 1 else None,
        "аннотация": clean_desc,
        # --- Мегамаркет (точные поля из документации и скриншота) ---
        "кодтоварапродавца": article,
        "кодтоварапродавцаofferid": article,
        "основнойштрихкодgtin": main_gtin,
        "штрихкод2": bc_parts[1] if len(bc_parts) > 1 else None,
        "штрихкод3": bc_parts[2] if len(bc_parts) > 2 else None,
        "штрихкод4": bc_parts[3] if len(bc_parts) > 3 else None,
        "штрихкод5": bc_parts[4] if len(bc_parts) > 4 else None,
        "ссылканаpdfинструкцию": attr_map.get("ссылканаpdfинструкцию") or None,
        "ссылканасертификат": attr_map.get("ссылканасертификат") or None,
        "названиетоварапоформулетиптоварабрендмодельартикул": product.get("name"),
        "urlосновногофото": photos[0] if photos else None,
        "urlфото2": photos[1] if len(photos) > 1 else None,
        "urlфото3": photos[2] if len(photos) > 2 else None,
        "urlфото4": photos[3] if len(photos) > 3 else None,
        "urlфото5": photos[4] if len(photos) > 4 else None,
        "urlфото6": photos[5] if len(photos) > 5 else None,
        "urlфото7": photos[6] if len(photos) > 6 else None,
        "urlфото8": photos[7] if len(photos) > 7 else None,
        "urlфото9": photos[8] if len(photos) > 8 else None,
        "urlфото10": photos[9] if len(photos) > 9 else None,
        # --- AliExpress (точные поля из документации и скриншотов) ---
        "модельsellerspuid": spu_id,
        "sellerspuid": spu_id,
        "артикулштрихкодsellerskuid": article,
        "артикулsellerskuid": article,
        "sellerskuid": article,
        "штрихкодean": main_gtin,
        "gtin": main_gtin,
        "главноефото": photos[0] if photos else None,
        "фотоsku": product.get("_variant_photo") or (photos[0] if photos else None),
        "цвет": var_color,
        "размер": var_size,
        "доставкаиз": "Российская Федерация",
        "названиецветавсистемепродавца": var_color,
        "названиеразмеравсистемепродавца": var_size,
        "вессупаковкой": weight_kg,
        "длинаупаковки": int(round(length_cm)) if length_cm else None,
        "ширинаупаковки": int(round(width_cm)) if width_cm else None,
        "высотаупаковки": int(round(height_cm)) if height_cm else None,
        # --- Яндекс Маркет / Холодильник.ру / Магнит ---
        "ссылканаизображение": ", ".join(photos[:30]) if photos else None,
        "ссылканафото": "; ".join(photos[:15])
        if platform != "yandex"
        else (", ".join(photos[:30]) if photos else None),
        "ссылкинафото": "; ".join(photos[:15]) if photos else None,
        "фотоurl": "; ".join(photos[:10]) if photos else None,
        "urlкартинки": photos[0] if photos else None,
        "описаниетовара": clean_desc[:6000] if clean_desc else None,
        "описание": clean_desc[:6000] if clean_desc else None,
        "категориянамаркете": cat_val,
        "категория": cat_val,
        "предмет": cat_val,
        "предметкатегория": cat_val,
        "бренд": brand_val,
        "производитель": brand_val,
        "производительбренд": brand_val,
        "штрихкод": barcode_comma
        if platform == "yandex"
        else (main_gtin if platform == "megamarket" else barcode_semi),
        "баркод": barcode_comma if platform == "yandex" else barcode_semi,
        "странапроизводства": attr_map.get("странапроизводства")
        or attr_map.get("странаизготовитель")
        or "Россия",
        "артикулпроизводителя": article,
        "вескг": _format_comma_decimal(weight_kg) if platform == "megamarket" else weight_kg,
        "весвупаковкекг": _format_comma_decimal(weight_kg)
        if platform == "megamarket"
        else weight_kg,
        "вессупаковкойкг": _format_comma_decimal(weight_kg)
        if platform == "megamarket"
        else weight_kg,
        "длинасм": _format_comma_decimal(length_cm) if platform == "megamarket" else length_cm,
        "длинаупаковкисм": _format_comma_decimal(length_cm)
        if platform == "megamarket"
        else length_cm,
        "ширинасм": _format_comma_decimal(width_cm) if platform == "megamarket" else width_cm,
        "ширинаупаковкисм": _format_comma_decimal(width_cm)
        if platform == "megamarket"
        else width_cm,
        "высотасм": _format_comma_decimal(height_cm) if platform == "megamarket" else height_cm,
        "высотаупаковкисм": _format_comma_decimal(height_cm)
        if platform == "megamarket"
        else height_cm,
        "габаритысупаковкойсм": dims_slash_cm,
        "товардоставляетсявнесколькихупаковках": int(units)
        if units and int(units) > 1
        else None,
        "цена": product.get("price"),
        "ценаруб": product.get("price"),
        "ценасучетомскидок": product.get("price"),
        "остаток": stock_val,
        "зачёркнутаяцена": product.get("strike_price"),
        "зачеркнутаяцена": product.get("strike_price"),
        "ценадоскидки": product.get("strike_price"),
        "тнвэд": okpd,
        "характеристикитовара": ym_characteristics,
        "вархиве": "Нет",
    }

    # Атрибуты товара — по нормализованному имени колонки
    for key, val in attr_map.items():
        if val not in (None, ""):
            values.setdefault(key, val)

    # Фолбэки-синонимы канонических колонок
    for b in BRAND_SYNONYMS:
        values.setdefault(b, brand_val)
    if not any(values.get(m) for m in MODEL_SYNONYMS):
        for m in MODEL_SYNONYMS:
            values[m] = spu_id if platform == "aliexpress" else product.get("name")
    if not any(values.get(m) for m in MARKING_SYNONYMS):
        values[MARKING_SYNONYMS[0]] = "Нет"
    if not values.get("количествовупаковке") and not values.get("количествовупаковкешт"):
        if units:
            values["количествовупаковке"] = units

    # Приведение значений к регистру словаря площадки и очистка разделителей
    for key, val in list(values.items()):
        if val in (None, "") or isinstance(val, (int, float)):
            continue
        s = str(val)
        if (
            platform in ("ozon", "megamarket")
            and (";" in s or "," in s)
            and key
            not in (
                "аннотация",
                "описание",
                "описаниетовара",
                "вескг",
                "весвупаковкекг",
                "вессупаковкойкг",
                "длинасм",
                "длинаупаковкисм",
                "ширинасм",
                "ширинаупаковкисм",
                "высотасм",
                "высотаупаковкисм",
            )
        ):
            s = "; ".join(p.strip() for p in re.split(r"[;,]", s) if p.strip())
            if platform == "ozon":
                s = _normalize_multi(s)
        fix = enum_fix.get(key)
        if fix:
            s = fix.get(s.strip().lower(), s)
        values[key] = s
    return values


def _build_enum_fix(spec: dict | None) -> dict[str, dict[str, str]]:
    fix: dict[str, dict[str, str]] = {}
    for a in (spec or {}).get("attributes") or []:
        vals = a.get("values") or []
        if vals:
            fix[_norm(a.get("name"))] = {str(v).strip().lower(): str(v) for v in vals}
    return fix


def _expand_products_for_platform(products: list, platform: str) -> list[dict]:
    """
    Для AliExpress и Мегамаркета: если у товара заданы вариации (`variants`),
    разворачивает их в отдельные строки с единым SPU ID (`_spu_id` / `Модель`)
    и индивидуальным SKU ID (`_article`), цветом и размером.
    """
    expanded: list[dict] = []
    seen: dict[str, int] = {}

    for p in products:
        base_sku = str(p.get("sku") or p.get("external_id") or f"ID{p.get('id')}").strip()
        seen[base_sku] = seen.get(base_sku, 0) + 1
        spu_id = base_sku if seen[base_sku] == 1 else f"{base_sku}_{seen[base_sku]}"

        variants = p.get("variants") or []
        if platform == "aliexpress" and len(variants) > 0:
            for idx, v in enumerate(variants, start=1):
                clone = dict(p)
                clone["_spu_id"] = spu_id
                v_sku = str(v.get("sku") or f"{spu_id}-{idx}").strip()
                clone["_article"] = v_sku
                clone["_variant_color"] = v.get("color") or ""
                clone["_variant_size"] = v.get("size") or v.get("name") or ""
                clone["_variant_photo"] = v.get("photo") or ""
                if v.get("price"):
                    clone["price"] = v["price"]
                if v.get("stock") is not None:
                    clone["stock"] = v["stock"]
                expanded.append(clone)
        else:
            clone = dict(p)
            clone["_spu_id"] = spu_id
            clone["_article"] = spu_id
            expanded.append(clone)

    return expanded


def _detect_aliexpress_custom_attr_cols(ws, header_row: int) -> list[int]:
    """
    Находит до 5 столбцов блока «Произвольные характеристики продавца» в шаблоне AliExpress
    (по тексту «Добавьте произвольную характеристику» в строке подсказок header_row - 1).
    """
    custom_cols: list[int] = []
    if header_row < 2:
        return custom_cols
    hint_row = header_row - 1
    for col in range(1, ws.max_column + 1):
        hint_val = str(ws.cell(row=hint_row, column=col).value or "").lower()
        if "произвольную характеристику" in hint_val:
            custom_cols.append(col)
    return custom_cols[:5]


# ==================== Заполнение эталона ====================


def fill_official_template(
    category_name: str,
    products: list,
    spec: dict | None = None,
    platform: str = "ozon",
) -> bytes:
    """
    Открывает эталонный файл площадки (Ozon / Яндекс Маркет / WB / Магнит /
    Мегамаркет / Холодильник.ру / AliExpress),
    удаляет демонстрационные строки-примеры и заполняет нашими товарами.
    """
    pl = (platform or "ozon").lower().strip()
    path = template_path(category_name, platform=pl)
    if not path:
        raise ValueError(
            f"Эталонный шаблон для площадки '{pl}' (категория '{category_name}') не загружен"
        )

    wb = load_workbook(io.BytesIO(path.read_bytes()))
    ws = _find_data_sheet(wb)

    header_row = _find_header_row(ws) or (3 if pl == "aliexpress" else 2)
    data_start_row = _detect_data_start_row(ws, header_row, pl)

    # Для AliExpress определяем 5 колонок «Произвольные характеристики продавца»
    ae_custom_cols = _detect_aliexpress_custom_attr_cols(ws, header_row) if pl == "aliexpress" else []

    # Сопоставляем нормализованные заголовки с номерами столбцов
    headers: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        if col in ae_custom_cols:
            continue
        h = ws.cell(row=header_row, column=col).value
        if h:
            norm_h = _norm(str(h).rstrip("*").strip())
            if norm_h and norm_h not in headers:
                headers[norm_h] = col

    # Зачищаем примеры («Дрель Makita», демо-свитера SW01 и т.д.) ниже шапки
    if ws.max_row >= data_start_row:
        ws.delete_rows(data_start_row, ws.max_row - data_start_row + 1)

    rows_to_write = _expand_products_for_platform(products, pl)

    # Если это AliExpress и есть колонки произвольных характеристик продавца —
    # выбираем до 5 дополнительных атрибутов, которых ещё нет среди стандартных колонок шаблона,
    # и записываем их названия в header_row (строку 3), как требует документация AliExpress.
    ae_custom_attr_names: list[tuple[int, str, str]] = []
    if ae_custom_cols and rows_to_write:
        skip_norms = set(headers.keys()) | {"бренд", "цвет", "размер", "модель", "тип"}
        collected: list[tuple[str, str]] = []
        seen_norms: set[str] = set()
        for p in rows_to_write:
            for a in p.get("attributes") or []:
                aname = (a.get("name") or "").strip()
                anorm = _norm(aname)
                if aname and anorm and anorm not in skip_norms and anorm not in seen_norms:
                    seen_norms.add(anorm)
                    collected.append((aname, anorm))
                    if len(collected) >= len(ae_custom_cols):
                        break
            if len(collected) >= len(ae_custom_cols):
                break
        for col_idx, (orig_name, norm_key) in zip(ae_custom_cols, collected):
            ws.cell(row=header_row, column=col_idx, value=orig_name)
            ae_custom_attr_names.append((col_idx, orig_name, norm_key))

    enum_fix = _build_enum_fix(spec)

    numeric_keys = {
        "весвупаковкег",
        "ширинаупаковкимм",
        "высотаупаковкимм",
        "длинаупаковкимм",
        "предельнаяценабезакцийруб",
        "зачёркнутаяценаруб",
        "зачеркнутаяценаруб",
        "вессупаковкой",
        "длинаупаковки",
        "ширинаупаковки",
        "высотаупаковки",
        "цена",
        "ценаруб",
        "ценасучетомскидок",
        "остаток",
        "зачёркнутаяцена",
        "зачеркнутаяцена",
    }
    if pl != "megamarket":
        numeric_keys |= {"вескг", "весвупаковкекг", "вессупаковкойкг", "длинасм", "ширинасм", "высотасм"}

    for i, product in enumerate(rows_to_write, start=1):
        values = _row_values(product, i, enum_fix, platform=pl)
        r = data_start_row + i - 1
        for key, col in headers.items():
            val = values.get(key)
            if val in (None, ""):
                continue
            if key in numeric_keys:
                try:
                    num = float(val)
                    val = int(num) if num == int(num) else num
                except (TypeError, ValueError):
                    pass
            ws.cell(row=r, column=col, value=val)

        # Заполняем значения произвольных характеристик продавца в шаблоне AliExpress
        for col_idx, _orig_name, norm_key in ae_custom_attr_names:
            cval = values.get(norm_key)
            if cval not in (None, ""):
                ws.cell(row=r, column=col_idx, value=str(cval))

    buf = io.BytesIO()
    wb.save(buf)
    logger.info(
        f"✅ Эталон [{pl}] ({path.name}): заполнено строк: {len(rows_to_write)} (со строки {data_start_row})"
    )
    return buf.getvalue()