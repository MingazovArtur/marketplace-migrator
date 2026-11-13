"""
Парсер файлов Ozon (XLSX).
Объединяет логику из file_parser.py, ozon_parser.py и ozon_import_parser.py.
"""

import io
import logging

import openpyxl

from .base import BaseFileParser, ParseResult
from .utils import (
    clean_okpd,
    clean_value,
    clean_vat,
    is_service_row,
    parse_int,
    parse_price,
    split_photos,
)

logger = logging.getLogger(__name__)


class OzonFileParser(BaseFileParser):
    """Парсер файлов Ozon (шаблоны и отчёты)."""

    @property
    def platform(self) -> str:
        return "ozon"

    @property
    def supported_formats(self) -> list[str]:
        return ["xlsx"]

    def parse(self, file_content: bytes, file_type: str) -> ParseResult:
        if file_type != "xlsx":
            raise ValueError("Для Ozon поддерживается только формат XLSX")

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
        except Exception as e:
            raise ValueError(f"Не удалось открыть XLSX файл: {e}") from e

        sheet_name = "Шаблон" if "Шаблон" in wb.sheetnames else wb.sheetnames[0]
        ws = wb[sheet_name]

        # 1. Поиск строки заголовков
        header_row_idx = None
        for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=50, values_only=True)):
            row_text = " ".join(str(cell).lower() for cell in row if cell is not None)
            if "артикул" in row_text and "название товара" in row_text:
                header_row_idx = idx + 1
                break

        if header_row_idx is None:
            raise ValueError("Не найдена строка заголовков (Артикул, Название товара) в файле Ozon")

        # 2. Маппинг колонок
        header_cells = list(ws[header_row_idx])
        headers = [
            str(cell.value).strip() if cell.value else f"col_{i}"
            for i, cell in enumerate(header_cells)
        ]

        ozon_mapping = {
            "name": ["название товара", "название"],
            "price": ["предельная цена без акций, руб.", "цена на сайте, ₽", "цена"],
            "sku": ["артикул", "артикул*"],
            "external_id": ["sku", "ozon product id"],
            "barcode": ["штрихкод (серийный номер / ean)", "штрихкод"],
            "okpd": ["тн вэд коды еаэс*", "тн вэд коды еаэс"],
            "weight": ["вес в упаковке, г*", "вес в упаковке, г"],
            "width": ["ширина упаковки, мм*", "ширина упаковки, мм"],
            "height": ["высота упаковки, мм*", "высота упаковки, мм"],
            "length": ["длина упаковки, мм*", "длина упаковки, мм"],
            "photo": ["ссылка на главное фото*", "ссылка на главное фото"],
            "photos": ["ссылки на дополнительные фото"],
            "brand": ["бренд*", "бренд", "бренд в одежде и обуви"],
            "category": ["категория"],
            "description": ["аннотация", "описание"],
        }

        col_indices = {}
        for key, candidates in ozon_mapping.items():
            for i, h in enumerate(headers):
                h_lower = h.lower().strip()
                if any(cand in h_lower for cand in candidates):
                    col_indices[key] = i
                    break

        if "name" not in col_indices or "sku" not in col_indices:
            raise ValueError("Не найдены обязательные колонки 'Артикул' или 'Название товара'")

        products = []
        errors = []

        # 3. Чтение данных
        for row_idx, row in enumerate(
            ws.iter_rows(min_row=header_row_idx + 1, values_only=True), start=header_row_idx + 1
        ):
            row_text = " ".join(str(cell).lower() for cell in row if cell is not None)

            if is_service_row(row_text) or not any(cell for cell in row):
                continue

            def get_val(key, *, row=row):
                # row=row: раннее связывание переменной цикла (B023) —
                # get_val вызывается только внутри своей итерации
                idx = col_indices.get(key)
                if idx is not None and idx < len(row):
                    val = row[idx]
                    return clean_value(val)
                return ""

            sku = get_val("sku")
            name = get_val("name")

            if not sku and not name:
                continue
            if not name:
                errors.append({"row": row_idx, "error": "Пустое название товара"})
                continue

            # Парсинг полей
            price = parse_price(get_val("price"))
            photos = []
            main_photo = get_val("photo")
            if main_photo:
                photos.extend(split_photos(main_photo))
            add_photos = get_val("photos")
            if add_photos:
                photos.extend(split_photos(add_photos))
            photos = list(dict.fromkeys(photos))[:15]

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
                "package_weight_grams": parse_int(get_val("weight")),
                "package_width_mm": parse_int(get_val("width")),
                "package_height_mm": parse_int(get_val("height")),
                "package_length_mm": parse_int(get_val("length")),
                "vat_rate": clean_vat(get_val("vat")),
                "okpd_code": clean_okpd(get_val("okpd")),
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
