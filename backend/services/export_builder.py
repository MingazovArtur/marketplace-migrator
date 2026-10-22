"""
Построитель файлов выгрузки в формате личных кабинетов площадок.
Форматы настраиваются ОДНИМ словарём EXPORT_FORMATS.
"""

import io
import logging
import re

import pandas as pd
from openpyxl.utils import get_column_letter

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


def _clean_megamarket_sku(sku: str) -> str:
    """В Коде товара продавца на Мегамаркете не должно быть символов # и %."""
    return re.sub(r"[#%]+", "_", str(sku or "")).strip()


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
    raw_sku = p.get("sku") or p.get("external_id") or f"SMM-{p['id']}"
    sku = _clean_megamarket_sku(raw_sku)

    raw_bc = str(p.get("barcode") or "").strip()
    bc_parts = [b.strip() for b in re.split(r"[;,]", raw_bc) if b.strip()]
    main_gtin = (
        bc_parts[0]
        if (bc_parts and not bc_parts[0].startswith("2"))
        else _generate_gtin_ean13(p, prefix="460")
    )
    second_bc = bc_parts[1] if len(bc_parts) > 1 else ""

    photos = [str(u).strip() for u in (p.get("photos") or []) if str(u).strip()]
    wg = p.get("package_weight_grams") or p.get("weight_grams") or 500
    l_mm = p.get("package_length_mm") or 200
    w_mm = p.get("package_width_mm") or 150
    h_mm = p.get("package_height_mm") or 100

    # Десятичные дроби на Мегамаркете пишутся через запятую (не более 2 знаков после запятой)
    weight_str = f"{round(float(wg) / 1000.0, 2):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    length_str = f"{round(float(l_mm) / 10.0, 2):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    width_str = f"{round(float(w_mm) / 10.0, 2):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    height_str = f"{round(float(h_mm) / 10.0, 2):.2f}".rstrip("0").rstrip(".").replace(".", ",")

    return {
        "Код товара продавца": sku,
        "Основной штрихкод (GTIN)": main_gtin,
        "Штрихкод 2": second_bc,
        "Ссылка на pdf-инструкцию": "",
        "Ссылка на сертификат": "",
        "Название товара по формуле: Тип товара+Бренд+Модель/Артикул": _limit(
            p["name"], r["name_max"]
        ),
        "Описание товара": _limit(_clean_html(p.get("description") or p["name"]), r["desc_max"]),
        "Бренд": p.get("brand") or "Без бренда",
        "Модель": p.get("name", "")[:50],
        "Артикул производителя": sku,
        "НДС": p.get("vat_rate") or "Не облагается",
        "Цена": p["price"],
        "Вес, кг": weight_str,
        "Длина, см": length_str,
        "Ширина, см": width_str,
        "Высота, см": height_str,
        "URL основного фото": photos[0] if photos else "",
        "URL фото 2": photos[1] if len(photos) > 1 else "",
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


def _aliexpress_row(p: dict) -> dict:
    r = _rules("aliexpress")
    raw_sku = str(p.get("sku") or p.get("external_id") or f"AE-{p['id']}")[:50]
    photos = [str(u).strip() for u in (p.get("photos") or []) if str(u).strip()]

    attr_map = {
        re.sub(r"[^a-zа-я0-9]", "", (a.get("name") or "").lower()): a.get("value")
        for a in (p.get("attributes") or [])
        if a.get("name")
    }
    variants = p.get("variants") or []
    first_var = variants[0] if variants else {}
    color_val = first_var.get("color") or attr_map.get("цвет") or "Разноцветный"
    size_val = first_var.get("size") or attr_map.get("размер") or ""

    wg = p.get("package_weight_grams") or p.get("weight_grams") or 500
    l_mm = p.get("package_length_mm") or 200
    w_mm = p.get("package_width_mm") or 150
    h_mm = p.get("package_height_mm") or 100

    return {
        "Модель (seller SPU ID)*": raw_sku,
        "Артикул/Штрихкод (seller SKU ID)*": raw_sku,
        "Штрихкод / EAN": p.get("barcode") or _generate_gtin_ean13(p, prefix="460"),
        "Наименование товара*": _limit(p["name"], r["name_max"]),
        "Описание*": _limit(_clean_html(p.get("description") or p["name"]), r["desc_max"]),
        "Бренд*": p.get("brand") or "NONE",
        "Главное фото*": photos[0] if photos else "",
        "Фото SKU": photos[0] if photos else "",
        "Цвет*": color_val,
        "Доставка из*": "Российская Федерация",
        "Размер": size_val,
        "Название цвета в системе продавца": color_val,
        "Название размера в системе продавца": size_val,
        "Цена*": p["price"],
        "Остаток*": p.get("stock") if p.get("stock") is not None else 10,
        "Вес с упаковкой*": round(max(float(wg), 100.0) / 1000.0, 2),
        "Длина упаковки*": max(int(round(float(l_mm) / 10.0)), 1),
        "Ширина упаковки*": max(int(round(float(w_mm) / 10.0)), 1),
        "Высота упаковки*": max(int(round(float(h_mm) / 10.0)), 1),
    }


EXPORT_FORMATS = {
    "magnit": {"sheet": "Товары", "row_mapper": _magnit_row},
    "ozon": {"sheet": "Товары", "row_mapper": _ozon_row},
    "wildberries": {"sheet": "Товары", "row_mapper": _wb_row},
    "yandex": {"sheet": "Товары", "row_mapper": _yandex_row},
    "megamarket": {"sheet": "Товары", "row_mapper": _megamarket_row},
    "holodilnik": {"sheet": "Товары", "row_mapper": _holodilnik_row},
    "aliexpress": {"sheet": "Шаблон", "row_mapper": _aliexpress_row},
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
        for i, col in enumerate(df.columns, start=1):
            col_letter = get_column_letter(i)
            ws.column_dimensions[col_letter].width = max(15, min(45, len(str(col)) + 10))

    output.seek(0)
    logger.info(f"📤 Сформирован файл выгрузки для {platform}: {len(rows)} товаров")
    return output