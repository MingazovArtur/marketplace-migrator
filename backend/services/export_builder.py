"""
Построитель файлов выгрузки в формате личных кабинетов площадок.
Форматы настраиваются ОДНИМ словарём EXPORT_FORMATS.
"""

import io
import logging
import re

from openpyxl.utils import get_column_letter

from services.export_validator import VALIDATION_RULES
from services.xlsx_io import rows_workbook

logger = logging.getLogger(__name__)


def _clean_html(text: str) -> str:
    """Убирает HTML-теги из описания, схлопывает пробелы."""
    if not text:
        return ""
    text = re.sub(r"(?i)<img[^>]*>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">")):
        text = text.replace(ent, ch)
    return re.sub(r"\s+", " ", text).strip()


def _limit(text: str, max_len: int) -> str:
    """Обрезает текст до лимита площадки."""
    if not text:
        return ""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _photos_str(p: dict, limit: int = 10) -> str:
    photos = p.get("photos") or []
    return "; ".join(str(u) for u in photos[:limit])


def _rules(platform: str) -> dict:
    return VALIDATION_RULES.get(platform, VALIDATION_RULES["ozon"])


def _generate_gtin_ean13(product: dict, prefix: str = "460") -> str:
    """
    Генерирует валидный 13-значный штрихкод GTIN / EAN-13 по стандарту GS1.
    Для Мегамаркета используется префикс 460 (так как коды на 2 отклоняются).
    """
    pid = int(product.get("id") or 1)
    base12 = f"{prefix}{pid:09d}"[:12]
    odd_sum = sum(int(base12[i]) for i in range(0, 12, 2))
    even_sum = sum(int(base12[i]) for i in range(1, 12, 2))
    check_digit = (10 - ((odd_sum + even_sum * 3) % 10)) % 10
    return f"{base12}{check_digit}"


def _magnit_row(p: dict) -> dict:
    r = _rules("magnit")
    return {
        "Артикул продавца": p.get("sku") or f"MM-{p['id']}",
        "Название товара": _limit(p["name"], r["name_max"]),
        "Категория": p.get("mapped_category") or p.get("category") or "Без категории",
        "Цена, руб": p["price"],
        "Остаток": p.get("stock") or 10,
        "Ссылка на фото": _photos_str(p, r["photos_max"]),
        "Описание": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


def _ozon_row(p: dict) -> dict:
    r = _rules("ozon")
    return {
        "Offer ID": p.get("sku") or f"OZ-{p['id']}",
        "Название": _limit(p["name"], r["name_max"]),
        "Цена": p["price"],
        "Категория": p.get("mapped_category") or p.get("category") or "",
        "Ссылка на фото": _photos_str(p, r["photos_max"]),
        "Описание": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


def _wb_row(p: dict) -> dict:
    r = _rules("wildberries")
    return {
        "Артикул продавца": p.get("sku") or f"WB-{p['id']}",
        "Наименование": _limit(p["name"], r["name_max"]),
        "Цена с учетом скидок": p["price"],
        "Предмет (категория)": p.get("mapped_category") or p.get("category") or "",
        "Ссылка на фото": _photos_str(p, r["photos_max"]),
        "Описание": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


def _yandex_row(p: dict) -> dict:
    r = _rules("yandex")
    return {
        "Артикул": p.get("sku") or f"YM-{p['id']}",
        "Название": _limit(p["name"], r["name_max"]),
        "Цена": p["price"],
        "Категория": p.get("mapped_category") or p.get("category") or "",
        "URL картинки": _photos_str(p, limit=1),
        "Описание": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


def _holodilnik_row(p: dict) -> dict:
    r = _rules("holodilnik")
    wg = p.get("package_weight_grams") or p.get("weight_grams") or 500
    l_mm = p.get("package_length_mm") or 200
    w_mm = p.get("package_width_mm") or 150
    h_mm = p.get("package_height_mm") or 100
    dims_cm = f"{round(float(l_mm)/10, 1)}x{round(float(w_mm)/10, 1)}x{round(float(h_mm)/10, 1)}"

    return {
        "Артикул": p.get("sku") or f"HL-{p['id']}",
        "Наименование товара": _limit(p["name"], r["name_max"]),
        "Производитель (Бренд)": p.get("brand") or "Нет бренда",
        "Категория": p.get("mapped_category") or p.get("category") or "",
        "Штрихкод (EAN-13)": p.get("barcode") or _generate_gtin_ean13(p, prefix="460"),
        "Цена, руб.": p["price"],
        "Остаток": p.get("stock") if p.get("stock") is not None else 10,
        "Вес в упаковке, кг": round(float(wg) / 1000.0, 2),
        "Габариты (ДхШхВ), см": dims_cm,
        "Ссылки на фото": _photos_str(p, r["photos_max"]),
        "Описание": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


EXPORT_FORMATS = {
    "magnit": {"sheet": "Товары", "row_mapper": _magnit_row},
    "ozon": {"sheet": "Товары", "row_mapper": _ozon_row},
    "wildberries": {"sheet": "Товары", "row_mapper": _wb_row},
    "yandex": {"sheet": "Товары", "row_mapper": _yandex_row},
    "holodilnik": {"sheet": "Товары", "row_mapper": _holodilnik_row},
}

# AliExpress и Мегамаркет собираются билдерами официальной структуры
# (services.xlsx_generator.aliexpress / megamarket) — в build_rows и build_upload_file.


def build_rows(products: list, platform: str) -> list:
    """Строки файла выгрузки (словари) — используется и для предпросмотра."""
    if platform == "aliexpress":
        from services.xlsx_generator.aliexpress import aliexpress_flat_rows

        return aliexpress_flat_rows(products)

    if platform == "megamarket":
        from services.xlsx_generator.megamarket import megamarket_flat_rows

        return megamarket_flat_rows(products)

    fmt = EXPORT_FORMATS.get(platform)
    if not fmt:
        raise ValueError(f"Нет формата файла выгрузки для площадки '{platform}'")
    return [fmt["row_mapper"](p) for p in products]


def build_upload_file(products: list, platform: str) -> io.BytesIO:
    """Собирает XLSX для загрузки в личный кабинет целевой площадки."""
    # AliExpress и Мегамаркет: книга в структуре официального шаблона площадки
    if platform in ("aliexpress", "megamarket"):
        if platform == "aliexpress":
            from services.xlsx_generator.aliexpress import build_aliexpress_workbook

            wb = build_aliexpress_workbook(products)
        else:
            from services.xlsx_generator.megamarket import build_megamarket_workbook

            wb = build_megamarket_workbook(products)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        logger.info(f"📤 Сформирован файл выгрузки для {platform}: {len(products)} товаров")
        return output

    fmt = EXPORT_FORMATS.get(platform)
    if not fmt:
        raise ValueError(f"Нет формата файла выгрузки для площадки '{platform}'")

    rows = build_rows(products, platform)

    sheet_name = fmt.get("sheet", "Товары")
    wb = rows_workbook(rows, sheet_name)
    ws = wb.active
    for i, col in enumerate(ws[1], start=1):
        col_letter = get_column_letter(i)
        ws.column_dimensions[col_letter].width = max(15, min(45, len(str(col.value)) + 10))

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    logger.info(f"📤 Сформирован файл выгрузки для {platform}: {len(rows)} товаров")
    return output
