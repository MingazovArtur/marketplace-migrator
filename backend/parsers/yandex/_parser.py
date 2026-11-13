"""Парсер файлов Яндекс Маркета: официальный XLSX-шаблон и плоские CSV.

Вынесено без изменений из монолита parsers/yandex.py (Р24). Методы класса
перенесены 1:1: поиск листа и строки заголовков, карта колонок шаблона
(точное совпадение без «*» → частичное), пропуск служебных строк и
примера Makita, плоский CSV через find_column.
"""

import io
import logging
from typing import Any

import openpyxl

from parsers.base import BaseFileParser, ParseResult
from parsers.tables import read_csv_table
from parsers.utils import (
    clean_okpd,
    clean_value,
    find_column,
    is_service_row,
    parse_price,
    parse_stock,
    split_photos,
)
from parsers.yandex._support import (
    YANDEX_SKIP_MARKERS,
    _cm_to_mm,
    _kg_to_grams,
    _parse_yandex_characteristics,
)

logger = logging.getLogger(__name__)


class YandexFileParser(BaseFileParser):
    """Парсер файлов Яндекс Маркета (XLSX-шаблоны ассортимента и плоские выгрузки)."""

    @property
    def platform(self) -> str:
        return "yandex"

    @property
    def supported_formats(self) -> list[str]:
        return ["xlsx", "csv"]

    def parse(self, file_content: bytes, file_type: str) -> ParseResult:
        if file_type == "csv":
            return self._parse_flat_csv(file_content)
        return self._parse_xlsx(file_content)

    def _parse_xlsx(self, file_content: bytes) -> ParseResult:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
        except Exception as e:
            raise ValueError(f"Не удалось открыть XLSX файл Яндекс Маркета: {e}")

        # Ищем лист с товарами («Список товаров», «Товары», «Офферы» или первый не-служебный лист)
        preferred_sheets = ("Список товаров", "Товары", "Офферы", "Шаблон")
        sheet_name = next((s for s in preferred_sheets if s in wb.sheetnames), None)
        if not sheet_name:
            skip_sheets = ("инструкция", "описание полей", "справочник")
            sheet_name = next(
                (s for s in wb.sheetnames if not any(k in s.lower() for k in skip_sheets)),
                wb.sheetnames[0],
            )

        ws = wb[sheet_name]

        # 1. Ищем строку заголовков (обычно строка 2, где есть «Ваш SKU *» и «Название товара *»)
        header_row_idx = None
        for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=30, values_only=True), start=1):
            row_cells = [str(c).lower().strip() for c in row if c is not None]
            row_text = " ".join(row_cells)
            if (
                ("ваш sku" in row_text and "название товара" in row_text)
                or ("артикул" in row_text and "название" in row_text)
                or ("наименование" in row_text and "цена" in row_text)
            ):
                header_row_idx = idx
                break

        if header_row_idx is None:
            wb.close()
            raise ValueError(
                "Не найдена строка заголовков («Ваш SKU *», «Название товара *») в файле Яндекс Маркета"
            )

        header_cells = list(ws[header_row_idx])
        headers = [
            str(cell.value).strip() if cell.value is not None else f"col_{i}"
            for i, cell in enumerate(header_cells)
        ]

        # 2. Карта колонок шаблона Яндекс Маркета (со скриншота)
        ym_mapping = {
            "sku": ["ваш sku *", "ваш sku", "артикул продавца", "артикул*", "артикул", "sku"],
            "name": ["название товара *", "название товара", "название", "наименование"],
            "photo": [
                "ссылка на изображение *",
                "ссылка на изображение",
                "ссылка на фото",
                "url картинки",
                "фото",
            ],
            "description": ["описание товара *", "описание товара", "описание"],
            "category": [
                "категория на маркете *",
                "категория на маркете",
                "категория *",
                "категория",
            ],
            "brand": ["бренд *", "бренд", "производитель"],
            "barcode": ["штрихкод *", "штрихкод", "баркод"],
            "weight_kg": ["вес, кг *", "вес, кг", "вес с упаковкой, кг *", "вес с упаковкой, кг"],
            "length_cm": ["длина, см *", "длина, см"],
            "width_cm": ["ширина, см *", "ширина, см"],
            "height_cm": ["высота, см *", "высота, см"],
            "units": ["товар доставляется в нескольких упаковках"],
            "price": ["цена *", "цена", "стоимость", "цена, руб"],
            "strike_price": ["зачёркнутая цена", "зачеркнутая цена", "цена до скидки"],
            "tnved": ["тн вэд *", "тн вэд", "код тн вэд"],
            "okpd2": ["окпд 2", "окпд2"],
            "characteristics": ["характеристики товара"],
            "external_id": ["артикул товара (sku)", "артикул маркета"],
            "stock": ["остаток", "количество"],
        }

        col_indices: dict[str, int] = {}
        headers_clean = [h.lower().rstrip("*").strip() for h in headers]

        for key, candidates in ym_mapping.items():
            # Сначала точное совпадение (без учёта '*')
            for cand in candidates:
                cand_clean = cand.lower().rstrip("*").strip()
                for i, h_clean in enumerate(headers_clean):
                    if h_clean == cand_clean:
                        col_indices[key] = i
                        break
                if key in col_indices:
                    break
            # Если точного нет — частичное
            if key not in col_indices:
                for cand in candidates:
                    cand_clean = cand.lower().rstrip("*").strip()
                    for i, h_clean in enumerate(headers_clean):
                        if cand_clean in h_clean:
                            col_indices[key] = i
                            break
                    if key in col_indices:
                        break

        if "name" not in col_indices:
            wb.close()
            raise ValueError("Не найдена обязательная колонка «Название товара *» в файле Яндекс Маркета")

        products: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        # 3. Читаем строки ниже заголовка (пропуская строку 3 с подсказками и строку 4 с примером Makita)
        for row_idx, row in enumerate(
            ws.iter_rows(min_row=header_row_idx + 1, values_only=True),
            start=header_row_idx + 1,
        ):
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue

            row_text = " ".join(str(cell).lower() for cell in row if cell is not None)
            if is_service_row(row_text) or any(m in row_text for m in YANDEX_SKIP_MARKERS):
                continue

            def get_val(k: str) -> str:
                idx = col_indices.get(k)
                if idx is not None and idx < len(row):
                    return clean_value(row[idx])
                return ""

            sku = get_val("sku")
            name = get_val("name")

            # Дополнительная защита от строки-примера (если её частично изменили)
            if sku == "123456" and "makita" in name.lower():
                continue

            if not sku and not name:
                continue
            if not name:
                errors.append({"row": row_idx, "error": "Пустое название товара"})
                continue

            price = parse_price(get_val("price"))
            photos = split_photos(get_val("photo"))[:30]
            tnved = clean_okpd(get_val("tnved")) or clean_okpd(get_val("okpd2"))
            attrs = _parse_yandex_characteristics(get_val("characteristics"))

            units_raw = get_val("units")
            try:
                units_per_item = int(float(units_raw)) if units_raw else 1
            except ValueError:
                units_per_item = 1

            product = {
                "name": name,
                "price": price,
                "sku": sku,
                "external_id": get_val("external_id") or sku,
                "barcode": get_val("barcode"),
                "description": get_val("description"),
                "photos": photos,
                "category": get_val("category") or "Не указана",
                "brand": get_val("brand"),
                "stock": parse_stock(get_val("stock")) if "stock" in col_indices else None,
                "package_weight_grams": _kg_to_grams(get_val("weight_kg")),
                "package_length_mm": _cm_to_mm(get_val("length_cm")),
                "package_width_mm": _cm_to_mm(get_val("width_cm")),
                "package_height_mm": _cm_to_mm(get_val("height_cm")),
                "okpd_code": tnved,
                "units_per_item": max(1, units_per_item),
                "attributes": attrs,
            }
            products.append(product)

        wb.close()

        return ParseResult(
            products=products,
            errors=errors,
            warnings=[],
            total_rows=len(products) + len(errors),
            imported=len(products),
            failed=len(errors),
        )

    def _parse_flat_csv(self, file_content: bytes) -> ParseResult:
        # кодировки (utf-8 -> windows-1251 -> replace) — внутри read_csv_table
        df = read_csv_table(file_content)

        if df.empty:
            return ParseResult(
                products=[],
                errors=[],
                warnings=[{"type": "empty", "message": "Файл пуст"}],
                total_rows=0,
                imported=0,
                failed=0,
            )

        columns = [str(c).strip() for c in list(df.columns)]
        df.columns = columns

        name_col = find_column(columns, ["Название товара *", "Название товара", "Название", "Наименование"])
        price_col = find_column(columns, ["Цена *", "Цена", "Стоимость"])
        sku_col = find_column(columns, ["Ваш SKU *", "Ваш SKU", "Артикул", "SKU"])
        category_col = find_column(columns, ["Категория на Маркете *", "Категория"])
        photo_col = find_column(columns, ["Ссылка на изображение *", "Ссылка на фото", "URL картинки", "Фото"])
        desc_col = find_column(columns, ["Описание товара *", "Описание товара", "Описание"])
        brand_col = find_column(columns, ["Бренд *", "Бренд", "Производитель"])
        barcode_col = find_column(columns, ["Штрихкод *", "Штрихкод"])

        if not name_col:
            raise ValueError("Не найдена колонка с названием товара для Яндекс Маркета")

        products: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for idx, row in df.iterrows():
            row_num = idx + 2
            name = clean_value(row.get(name_col))
            if not name:
                errors.append({"row": row_num, "error": "Пустое название товара"})
                continue

            products.append(
                {
                    "name": name,
                    "price": parse_price(clean_value(row.get(price_col))) if price_col else 0.0,
                    "sku": clean_value(row.get(sku_col)) if sku_col else "",
                    "barcode": clean_value(row.get(barcode_col)) if barcode_col else "",
                    "description": clean_value(row.get(desc_col)) if desc_col else "",
                    "photos": split_photos(clean_value(row.get(photo_col))) if photo_col else [],
                    "category": clean_value(row.get(category_col)) if category_col else "Не указана",
                    "brand": clean_value(row.get(brand_col)) if brand_col else "",
                }
            )

        return ParseResult(
            products=products,
            errors=errors,
            warnings=[],
            total_rows=len(df),
            imported=len(products),
            failed=len(errors),
        )
