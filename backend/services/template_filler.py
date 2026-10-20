"""
Мультиплатформенное хранилище и заполнение ЭТАЛОННЫХ шаблонов площадок
(Ozon, Яндекс Маркет, Wildberries, Магнит Маркет, Мегамаркет, Poizon,
Холодильник.ру, Страна.маркет, UDS).

Пользователь скачивает официальный XLSX-шаблон в кабинете площадки и загружает
его в разделе «Шаблоны». При выгрузке мы открываем этот файл как КАРКАС:
все листы («Инструкция», «Список товаров», «Шаблон», скрытые словари), шапка,
стили, выпадающие списки и метаданные остаются 100% оригинальными — мы только
удаляем строку-пример (например, «Дрель Makita» в Яндексе) и записываем товары
в соответствующие столбцы.

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
    "model",
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


def _generate_ean13(product: dict) -> str:
    """Генерирует валидный 13-значный штрихкод EAN-13 по стандарту GS1."""
    pid = int(product.get("id") or 1)
    base12 = f"200{pid:09d}"[:12]
    odd_sum = sum(int(base12[i]) for i in range(0, 12, 2))
    even_sum = sum(int(base12[i]) for i in range(1, 12, 2))
    check_digit = (10 - ((odd_sum + even_sum * 3) % 10)) % 10
    return f"{base12}{check_digit}"


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
        (["толстовк", "худи", "свитшот", "джемпер", "свитер"], "Толстовки, свитшоты и худи"),
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
        "Products",
        "Assortment",
        "Каталог",
    ):
        if candidate in wb.sheetnames:
            return wb[candidate]
    skip_words = ("инструкция", "описание полей", "справочник", "видео", "документация", "правила", "readme", "help")
    for name in wb.sheetnames:
        if not any(w in name.lower() for w in skip_words):
            return wb[name]
    return wb.active


def _find_header_row(ws) -> int | None:
    """Ищет строку заголовков (по колонкам «Артикул», «Ваш SKU», «Seller SKU», «Код товара продавца», «Наименование»)."""
    header_markers = {
        "артикул",
        "вашsku",
        "sellerskuid",
        "sellersku",
        "артикулпродавца",
        "артикулsku",
        "кодтоварапродавца",
        "кодтоварапродавцаofferid",
        "offerid",
        "sku",
        "наименование",
        "наименованиетовара",
        "названиетовара",
        "producttitle",
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
    Определяет строку, с которой начинаются товары (и откуда нужно удалить примеры площадки):
    - В Яндекс Маркете: строка 2 — заголовки, строка 3 — подсказки, строка 4 — пример («Дрель Makita»).
      Значит, данные начинаются с 4-й строки (header_row + 2).
    - В Ozon: строка 2 — заголовки, строка 3 — «Обязательное поле», строка 4 — подсказки,
      данные с 5-й строки (header_row + 3).
    """
    if platform == "yandex":
        return header_row + 2

    # Проверяем, есть ли в строке header_row + 1 маркеры Ozon («Обязательное поле» / «Рекомендуем»)
    row_plus_1_text = " ".join(
        str(c.value).lower() for c in ws[header_row + 1] if c.value is not None
    )
    if "обязательное поле" in row_plus_1_text or "рекомендуем к заполнению" in row_plus_1_text:
        return header_row + 3

    # Проверяем, является ли строка header_row + 1 длинной строкой подсказок (как в Яндексе или Мегамаркете)
    if any(
        m in row_plus_1_text
        for m in (
            "уникальный идентификатор",
            "значение поля выгружено",
            "заполняется автоматически",
            "обязательный параметр",
            "необязательный параметр",
        )
    ):
        return header_row + 2

    return header_row + 1 if header_row == 1 else 5


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
      2. Совпадение по конечному типу категории (например, «Одежда / Футболки» -> «Футболки»).
      3. Универсальный шаблон площадки («Универсальный», «Общий», «Все категории»).
      4. Фолбэк: первый доступный шаблон этой площадки.
    """
    pl = (platform or "ozon").lower().strip()
    cat = (category_name or "").strip()
    idx = _load_index()

    # Собираем все существующие на диске шаблоны этой площадки
    platform_templates: list[dict] = []
    for meta in idx.values():
        if meta.get("platform") == pl and (TEMPLATES_DIR / meta["file"]).exists():
            platform_templates.append(meta)

    if not platform_templates:
        return None

    # 1. Точное совпадение имени категории
    if cat:
        for m in platform_templates:
            if m["category_name"].lower() == cat.lower():
                return m

        # 2. Совпадение по последней части пути («Родитель / Тип»)
        cat_leaf = cat.split("/")[-1].strip().lower()
        for m in platform_templates:
            m_leaf = m["category_name"].split("/")[-1].strip().lower()
            if cat_leaf and m_leaf == cat_leaf:
                return m

    # 3. Универсальный шаблон площадки
    for m in platform_templates:
        if m["category_name"].strip().lower() in UNIVERSAL_NAMES:
            return m

    # 4. Фолбэк: используем первый загруженный шаблон этой площадки
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
                "«Ваш SKU *», «Код товара продавца», «Seller SKU» или «Наименование»)"
            )
        return None
    finally:
        wb.close()


# ==================== Значения строки товара (Все 9 площадок) ====================


def _row_values(
    product: dict,
    row_num: int,
    enum_fix: dict[str, dict[str, str]],
    platform: str = "ozon",
) -> dict[str, object]:
    """
    Формирует словарь значений строки товара для любой из 9 поддерживаемых площадок.
    Ключи — нормализованные имена колонок (без звёздочек, знаков препинания и пробелов).
    """
    photos = [str(u).strip() for u in (product.get("photos") or []) if str(u).strip()]
    attr_map = {
        _norm(a.get("name")): a.get("value")
        for a in (product.get("attributes") or [])
        if a.get("name")
    }

    article = (
        product.get("_article")
        or product.get("sku")
        or product.get("external_id")
        or f"ID{product.get('id')}"
    )
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
        "noname",
        "no name",
    ):
        brand_val = "NoBrand" if platform == "poizon" else "Нет бренда"
    else:
        brand_val = raw_brand

    # Штрихкод (автогенерация EAN-13 при отсутствии)
    raw_bc = product.get("barcode") or attr_map.get("штрихкод") or ""
    bc_parts = [p.strip() for p in re.split(r"[;,]", str(raw_bc)) if p.strip()]
    if not bc_parts and platform in (
        "yandex",
        "wildberries",
        "megamarket",
        "poizon",
        "holodilnik",
        "strana",
    ):
        for v in product.get("variants") or []:
            v_sku = str(v.get("sku") or "").strip()
            if v_sku.isdigit() and 8 <= len(v_sku) <= 14:
                bc_parts = [v_sku]
                break
        if not bc_parts:
            bc_parts = [_generate_ean13(product)]

    barcode_semi = ";".join(bc_parts) if bc_parts else None
    barcode_comma = ", ".join(bc_parts) if bc_parts else None

    # Вес и габариты (в граммах/мм и в кг/см)
    wg = product.get("package_weight_grams") or product.get("weight_grams")
    l_mm = product.get("package_length_mm")
    w_mm = product.get("package_width_mm")
    h_mm = product.get("package_height_mm")

    weight_kg = round(float(wg) / 1000.0, 3) if wg else None
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
    vat_val = VAT_LABELS.get(str(product.get("vat_rate") or ""), product.get("vat_rate") or "Не облагается")

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
        "кодтоварапродавца": article,
        "кодтоварапродавцаofferid": article,
        "offerid": article,
        "sellersku": article,
        "sellerskuid": article,
        "вашsku": article,
        "названиетовара": product.get("name"),
        "название": product.get("name"),
        "наименование": product.get("name"),
        "наименованиетовара": product.get("name"),
        "producttitle": product.get("name"),
        "title": product.get("name"),
        "предельнаяценабезакцийруб": product.get("price"),
        "зачёркнутаяценаруб": product.get("strike_price"),
        "зачеркнутаяценаруб": product.get("strike_price"),
        "ндс": vat_val,
        "штрихкодсерийныйномерean": barcode_semi,
        "штрихкодbarcode": barcode_semi,
        "штрихкодean13": barcode_semi,
        "barcodeean": barcode_semi,
        "barcode": barcode_semi,
        "тнвэдкодыеаэс": okpd,
        "весвупаковкег": wg,
        "ширинаупаковкимм": w_mm,
        "высотаупаковкимм": h_mm,
        "длинаупаковкимм": l_mm,
        "ссылканаглавноефото": photos[0] if photos else None,
        "ссылкинадополнительныефото": " ".join(photos[1:15]) if len(photos) > 1 else None,
        "аннотация": clean_desc,
        # --- Яндекс Маркет / Мегамаркет / Холодильник / Страна / UDS / Poizon ---
        "ссылканаизображение": ", ".join(photos[:30]) if photos else None,
        "ссылканафото": "; ".join(photos[:15]) if platform != "yandex" else (", ".join(photos[:30]) if photos else None),
        "ссылкинафото": "; ".join(photos[:15]) if photos else None,
        "фотоurl": "; ".join(photos[:10]) if photos else None,
        "urlкартинки": photos[0] if photos else None,
        "imageurls": "; ".join(photos[:12]) if photos else None,
        "описаниетовара": clean_desc[:6000] if clean_desc else None,
        "описание": clean_desc[:6000] if clean_desc else None,
        "description": clean_desc[:3000] if clean_desc else None,
        "категориянамаркете": cat_val,
        "категория": cat_val,
        "предмет": cat_val,
        "предметкатегория": cat_val,
        "category": cat_val,
        "бренд": brand_val,
        "производитель": brand_val,
        "производительбренд": brand_val,
        "brand": brand_val,
        "штрихкод": barcode_comma if platform == "yandex" else barcode_semi,
        "баркод": barcode_comma if platform == "yandex" else barcode_semi,
        "странапроизводства": attr_map.get("странапроизводства")
        or attr_map.get("странаизготовитель")
        or "Россия",
        "артикулпроизводителя": article,
        "вескг": weight_kg,
        "вессупаковкойкг": weight_kg,
        "длинасм": length_cm,
        "ширинасм": width_cm,
        "высотасм": height_cm,
        "габаритысупаковкойсм": dims_slash_cm,
        "товардоставляетсявнесколькихупаковках": int(units) if units and int(units) > 1 else None,
        "цена": product.get("price"),
        "ценаруб": product.get("price"),
        "ценасучетомскидок": product.get("price"),
        "price": product.get("price"),
        "остаток": stock_val,
        "stock": stock_val,
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
            values[m] = product.get("name")
    if not any(values.get(m) for m in MARKING_SYNONYMS):
        values[MARKING_SYNONYMS[0]] = "Нет"
    if not values.get("количествовупаковке") and not values.get("количествовупаковкешт"):
        if units:
            values["количествовупаковке"] = units

    # Приведение значений к регистру словаря площадки
    for key, val in list(values.items()):
        if val in (None, "") or isinstance(val, (int, float)):
            continue
        s = str(val)
        if platform == "ozon" and (";" in s or "," in s) and key not in ("аннотация", "описание"):
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


# ==================== Заполнение эталона ====================


def fill_official_template(
    category_name: str,
    products: list,
    spec: dict | None = None,
    platform: str = "ozon",
) -> bytes:
    """
    Открывает эталонный файл площадки (Ozon / Яндекс Маркет / WB / Магнит /
    Мегамаркет / Poizon / Холодильник.ру / Страна.маркет / UDS),
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

    header_row = _find_header_row(ws) or 2
    data_start_row = _detect_data_start_row(ws, header_row, pl)

    # Сопоставляем нормализованные заголовки с номерами столбцов
    headers: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        h = ws.cell(row=header_row, column=col).value
        if h:
            norm_h = _norm(str(h).rstrip("*").strip())
            if norm_h and norm_h not in headers:
                headers[norm_h] = col

    # Зачищаем примеры («Дрель Makita» и т.д.) / старые данные ниже шапки
    if ws.max_row >= data_start_row:
        ws.delete_rows(data_start_row, ws.max_row - data_start_row + 1)

    # Уникализация артикулов
    seen: dict[str, int] = {}
    for p in products:
        base = p.get("sku") or p.get("external_id") or f"ID{p.get('id')}"
        seen[base] = seen.get(base, 0) + 1
        p["_article"] = base if seen[base] == 1 else f"{base}_{seen[base]}"

    enum_fix = _build_enum_fix(spec)

    numeric_keys = {
        "весвупаковкег",
        "ширинаупаковкимм",
        "высотаупаковкимм",
        "длинаупаковкимм",
        "предельнаяценабезакцийруб",
        "зачёркнутаяценаруб",
        "зачеркнутаяценаруб",
        "вескг",
        "вессупаковкойкг",
        "длинасм",
        "ширинасм",
        "высотасм",
        "цена",
        "ценаруб",
        "ценасучетомскидок",
        "price",
        "остаток",
        "stock",
        "зачёркнутаяцена",
        "зачеркнутаяцена",
    }

    for i, product in enumerate(products, start=1):
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

    buf = io.BytesIO()
    wb.save(buf)
    logger.info(
        f"✅ Эталон [{pl}] ({path.name}): заполнено товаров: {len(products)} (со строки {data_start_row})"
    )
    return buf.getvalue()