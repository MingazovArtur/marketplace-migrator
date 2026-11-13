"""
Парсер файлов Магнит Маркет (XLSX).
"""

import logging
from typing import Any

from .base import BaseFileParser, ParseResult
from .tables import ExcelBook, Table
from .utils import (
    clean_value,
    find_column,
    is_service_row,
    parse_price,
    parse_stock,
    split_photos,
)

logger = logging.getLogger(__name__)


class MagnitFileParser(BaseFileParser):
    """Парсер файлов Магнит Маркет."""

    @property
    def platform(self) -> str:
        return "magnit"

    @property
    def supported_formats(self) -> list[str]:
        return ["xlsx"]

    def parse(self, file_content: bytes, file_type: str) -> ParseResult:
        if file_type != "xlsx":
            raise ValueError("Для Магнит Маркета поддерживается только формат XLSX")

        xls = ExcelBook(file_content)

        # Поиск листа с данными
        data_sheet = None
        skip_keywords = ["инструкция", "бренд", "справочник", "шаблон", "пример"]

        for sheet_name in xls.sheet_names:
            sheet_lower = sheet_name.lower()
            if any(skip in sheet_lower for skip in skip_keywords):
                continue

            try:
                df_tmp = xls.parse(sheet_name=sheet_name, header=None, nrows=30)
            except Exception:
                continue

            for _, row in df_tmp.iterrows():
                row_text = " ".join(str(v).lower() for v in row.values if v is not None)
                if any(marker in row_text for marker in ["не менять", "не изменяйте"]):
                    continue
                if "название товара" in row_text or (
                    "название" in row_text and "артикул" in row_text
                ):
                    data_sheet = sheet_name
                    break

            if data_sheet:
                break

        if data_sheet is None:
            raise ValueError("Не найден лист с данными товаров в файле Магнит Маркета.")

        df = xls.parse(sheet_name=data_sheet, header=None)

        # Поиск строки заголовков
        header_row_idx = None
        for idx, row in df.iterrows():
            row_text = " ".join(str(v).lower() for v in row.values if v is not None)
            if any(marker in row_text for marker in ["не менять", "не изменяйте"]):
                continue
            if "название товара" in row_text or ("название" in row_text and "артикул" in row_text):
                header_row_idx = idx
                break

        if header_row_idx is None:
            raise ValueError("Не найдена строка заголовков в файле Магнит Маркета")

        header_row = df.iloc[header_row_idx]
        headers = [
            str(v).strip() if v is not None else f"col_{i}" for i, v in enumerate(header_row.values)
        ]

        data = df.iloc[header_row_idx + 1 :]
        data.columns = headers

        # Фильтрация служебных строк (сохраняем исходные индексы для номеров строк)
        filtered_rows: list[tuple[int, Any]] = []
        for idx, row in data.iterrows():
            row_text = " ".join(str(v).lower() for v in row.values if v is not None)
            if is_service_row(row_text):
                continue
            non_empty = [str(v).strip() for v in row.values if v is not None and str(v).strip()]
            if not non_empty:
                continue
            filtered_rows.append((idx, row))

        if not filtered_rows:
            return ParseResult(
                products=[],
                errors=[],
                warnings=[{"type": "empty", "message": "Файл не содержит данных о товарах"}],
                total_rows=0,
                imported=0,
                failed=0,
            )

        filtered_df = Table(columns=headers, rows=[row.values for _, row in filtered_rows])

        # Маппинг колонок Магнит
        magnit_mapping = {
            "name": ["Название товара", "Название", "Наименование"],
            "price": ["Цена", "Цена, руб", "Цена продажи"],
            "sku": ["Seller SKU ID", "SellerSKU", "SKU ID", "Артикул продавца", "Артикул"],
            "external_id": ["Product ID", "Продукт ID", "ID товара"],
            "barcode": ["ШК", "Баркод", "Штрихкод"],
            "category": ["Категория", "Раздел"],
            "photo": ["Фото (общее)", "Фото", "Ссылка на фото", "Ссылки на фото"],
            "photo_sku": ["Фото SKU"],
            "desc": ["Описание товара", "Описание"],
            "short_desc": ["Краткое описание"],
            "brand": ["Бренд"],
            "stock": ["Остаток"],
            "okpd2": ["ОКПД2"],
            "tn_ved": ["ТН ВЭД", "ТНВЭД"],
        }

        cols = list(filtered_df.columns)
        name_col = find_column(cols, magnit_mapping["name"])
        price_col = find_column(cols, magnit_mapping["price"])
        sku_col = find_column(cols, magnit_mapping["sku"])
        external_id_col = find_column(cols, magnit_mapping["external_id"])
        barcode_col = find_column(cols, magnit_mapping["barcode"])
        category_col = find_column(cols, magnit_mapping["category"])
        photo_col = find_column(cols, magnit_mapping["photo"])
        photo_sku_col = find_column(cols, magnit_mapping.get("photo_sku", []))
        desc_col = find_column(cols, magnit_mapping["desc"])
        short_desc_col = find_column(cols, magnit_mapping["short_desc"])
        brand_col = find_column(cols, magnit_mapping["brand"])
        stock_col = find_column(cols, magnit_mapping["stock"])
        okpd2_col = find_column(cols, magnit_mapping["okpd2"])
        tn_ved_col = find_column(cols, magnit_mapping["tn_ved"])

        if not name_col:
            raise ValueError("Не найдена колонка 'Название товара' в файле Магнит Маркета")

        products: list[dict] = []
        errors: list[dict] = []

        for orig_idx, row in filtered_rows:
            row_num = orig_idx + 2
            name = clean_value(row.get(name_col))

            if not name:
                errors.append({"row": row_num, "error": "Пустое название товара"})
                continue

            price = parse_price(clean_value(row.get(price_col))) if price_col else 0.0

            photos: list[str] = []
            if photo_col:
                photos.extend(split_photos(clean_value(row.get(photo_col))))
            if photo_sku_col:
                photos.extend(split_photos(clean_value(row.get(photo_sku_col))))
            photos = list(dict.fromkeys(photos))[:10]

            description = clean_value(row.get(desc_col)) if desc_col else ""
            if not description and short_desc_col:
                description = clean_value(row.get(short_desc_col))

            sku = clean_value(row.get(sku_col)) if sku_col else ""
            if not sku and barcode_col:
                sku = clean_value(row.get(barcode_col))

            product = {
                "name": name,
                "price": price,
                "sku": sku,
                "external_id": clean_value(row.get(external_id_col)) if external_id_col else "",
                "barcode": clean_value(row.get(barcode_col)) if barcode_col else "",
                "description": description,
                "photos": photos,
                "category": clean_value(row.get(category_col)) if category_col else "Не указана",
                "brand": clean_value(row.get(brand_col)) if brand_col else "",
                "stock": parse_stock(clean_value(row.get(stock_col))) if stock_col else 0,
                "okpd2": clean_value(row.get(okpd2_col)) if okpd2_col else "",
                "tn_ved": clean_value(row.get(tn_ved_col)) if tn_ved_col else "",
            }
            products.append(product)

        warnings = []
        if products and all(p["price"] == 0 for p in products):
            warnings.append(
                {
                    "type": "magnit_no_price",
                    "message": "В файле Магнит Маркета нет цен или все цены равны 0. Задайте цены вручную после импорта.",
                }
            )

        return ParseResult(
            products=products,
            errors=errors,
            warnings=warnings,
            total_rows=len(filtered_rows),
            imported=len(products),
            failed=len(errors),
        )
