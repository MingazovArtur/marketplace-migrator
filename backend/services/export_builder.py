"""
Построитель файлов выгрузки в формате личных кабинетов площадок.
Форматы настраиваются ОДНИМ словарём EXPORT_FORMATS.
"""

import io
import logging
import re

import pandas as pd

from services.export_validator import VALIDATION_RULES

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


def _megamarket_row(p: dict) -> dict:
    r = _rules("megamarket")
    return {
        "Код товара продавца (offerId)": p.get("sku") or f"SMM-{p['id']}",
        "Название товара": _limit(p["name"], r["name_max"]),
        "Бренд": p.get("brand") or "Нет бренда",
        "Штрихкод (Barcode)": p.get("barcode") or "",
        "Категория": p.get("mapped_category") or p.get("category") or "",
        "Цена, руб": p["price"],
        "НДС": p.get("vat_rate") or "Не облагается",
        "Остаток": p.get("stock") if p.get("stock") is not None else 10,
        "Ссылка на фото": _photos_str(p, r["photos_max"]),
        "Описание": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


def _poizon_row(p: dict) -> dict:
    r = _rules("poizon")
    return {
        "Seller SKU": p.get("sku") or f"PZ-{p['id']}",
        "Product Title": _limit(p["name"], r["name_max"]),
        "Brand": p.get("brand") or "NoBrand",
        "Category": p.get("mapped_category") or p.get("category") or "",
        "Barcode / EAN": p.get("barcode") or "",
        "Price": p["price"],
        "Stock": p.get("stock") if p.get("stock") is not None else 10,
        "Image URLs": _photos_str(p, r["photos_max"]),
        "Description": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


def _holodilnik_row(p: dict) -> dict:
    r = _rules("holodilnik")
    return {
        "Артикул": p.get("sku") or f"HL-{p['id']}",
        "Наименование товара": _limit(p["name"], r["name_max"]),
        "Производитель (Бренд)": p.get("brand") or "Нет бренда",
        "Категория": p.get("mapped_category") or p.get("category") or "",
        "Штрихкод (EAN-13)": p.get("barcode") or "",
        "Цена, руб.": p["price"],
        "Остаток": p.get("stock") if p.get("stock") is not None else 10,
        "Ссылки на фото": _photos_str(p, r["photos_max"]),
        "Описание": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


def _strana_row(p: dict) -> dict:
    r = _rules("strana")
    return {
        "Артикул продавца": p.get("sku") or f"SM-{p['id']}",
        "Наименование": _limit(p["name"], r["name_max"]),
        "Бренд": p.get("brand") or "Нет бренда",
        "Категория": p.get("mapped_category") or p.get("category") or "",
        "Штрихкод": p.get("barcode") or "",
        "Цена, руб": p["price"],
        "Остаток": p.get("stock") if p.get("stock") is not None else 10,
        "Ссылка на фото": _photos_str(p, r["photos_max"]),
        "Описание": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


def _uds_row(p: dict) -> dict:
    r = _rules("uds")
    return {
        "Артикул (SKU)": p.get("sku") or f"UDS-{p['id']}",
        "Название товара": _limit(p["name"], r["name_max"]),
        "Категория": p.get("mapped_category") or p.get("category") or "Товары",
        "Цена": p["price"],
        "Остаток": p.get("stock") if p.get("stock") is not None else 10,
        "Фото (URL)": _photos_str(p, r["photos_max"]),
        "Описание": _limit(_clean_html(p.get("description")), r["desc_max"]),
    }


EXPORT_FORMATS = {
    "magnit": {"sheet": "Товары", "row_mapper": _magnit_row},
    "ozon": {"sheet": "Товары", "row_mapper": _ozon_row},
    "wildberries": {"sheet": "Товары", "row_mapper": _wb_row},
    "yandex": {"sheet": "Товары", "row_mapper": _yandex_row},
    "megamarket": {"sheet": "Товары", "row_mapper": _megamarket_row},
    "poizon": {"sheet": "Products", "row_mapper": _poizon_row},
    "holodilnik": {"sheet": "Товары", "row_mapper": _holodilnik_row},
    "strana": {"sheet": "Товары", "row_mapper": _strana_row},
    "uds": {"sheet": "Товары", "row_mapper": _uds_row},
}


def build_rows(products: list, platform: str) -> list:
    """Строки файла выгрузки (словари) — используется и для предпросмотра."""
    fmt = EXPORT_FORMATS.get(platform)
    if not fmt:
        raise ValueError(f"Нет формата файла выгрузки для площадки '{platform}'")
    return [fmt["row_mapper"](p) for p in products]


def build_upload_file(products: list, platform: str) -> io.BytesIO:
    """Собирает XLSX для загрузки в личный кабинет целевой площадки."""
    fmt = EXPORT_FORMATS.get(platform)
    if not fmt:
        raise ValueError(f"Нет формата файла выгрузки для площадки '{platform}'")

    rows = build_rows(products, platform)
    df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        sheet_name = fmt.get("sheet", "Товары")
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]
        for i, col in enumerate(df.columns):
            ws.column_dimensions[chr(65 + i)].width = max(15, min(45, len(str(col)) + 10))

    output.seek(0)
    logger.info(f"📤 Сформирован файл выгрузки для {platform}: {len(rows)} товаров")
    return output