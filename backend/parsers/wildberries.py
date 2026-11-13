"""
Парсер плоских файлов (CSV/XLSX) для Wildberries и Яндекс Маркета.
"""
import logging

from .base import BaseFileParser, ParseResult
from .tables import read_csv_table, read_excel_table
from .utils import clean_value, find_column, parse_price, parse_stock, split_photos

logger = logging.getLogger(__name__)


class WBFileParser(BaseFileParser):
    """Парсер файлов Wildberries."""

    @property
    def platform(self) -> str:
        return "wildberries"

    @property
    def supported_formats(self) -> list[str]:
        return ["csv", "xlsx"]

    def parse(self, file_content: bytes, file_type: str) -> ParseResult:
        return self._parse_flat(file_content, file_type)

    def _parse_flat(self, file_content: bytes, file_type: str) -> ParseResult:
        # кодировки (utf-8 -> windows-1251 -> replace) — внутри read_csv_table
        df = read_csv_table(file_content) if file_type == "csv" else read_excel_table(file_content)

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

        wb_mapping = {
            "name": ["Название товара", "Название", "Наименование"],
            "price": ["Цена", "Цена, руб", "Цена продажи", "Стоимость"],
            "sku": ["Артикул", "Артикул продавца", "Баркод"],
            "category": ["Категория", "Раздел", "Предмет"],
            "photo": ["Ссылка на фото", "Фото", "Ссылки на фото"],
            "desc": ["Описание"],
            "brand": ["Бренд"],
            "stock": ["Остаток"],
        }

        name_col = find_column(columns, wb_mapping["name"])
        price_col = find_column(columns, wb_mapping["price"])
        sku_col = find_column(columns, wb_mapping["sku"])
        category_col = find_column(columns, wb_mapping["category"])
        photo_col = find_column(columns, wb_mapping["photo"])
        desc_col = find_column(columns, wb_mapping["desc"])
        brand_col = find_column(columns, wb_mapping["brand"])
        stock_col = find_column(columns, wb_mapping["stock"])

        if not name_col:
            raise ValueError("Не найдена колонка с названием товара для платформы 'wildberries'")

        products: list[dict] = []
        errors: list[dict] = []

        for idx, row in df.iterrows():
            row_num = idx + 2
            name = clean_value(row.get(name_col))

            if not name:
                errors.append({"row": row_num, "error": "Пустое название товара"})
                continue

            price = 0.0
            if price_col:
                price = parse_price(clean_value(row.get(price_col)))

            photos = []
            if photo_col:
                photos = split_photos(clean_value(row.get(photo_col)))

            description = clean_value(row.get(desc_col)) if desc_col else ""
            category = clean_value(row.get(category_col)) if category_col else "Не указана"
            brand = clean_value(row.get(brand_col)) if brand_col else ""
            stock = parse_stock(clean_value(row.get(stock_col))) if stock_col else 0
            sku = clean_value(row.get(sku_col)) if sku_col else ""

            product = {
                "name": name,
                "price": price,
                "sku": sku,
                "description": description,
                "photos": photos,
                "category": category,
                "brand": brand,
                "stock": stock,
            }
            products.append(product)

        return ParseResult(
            products=products,
            errors=errors,
            warnings=[],
            total_rows=len(df),
            imported=len(products),
            failed=len(errors),
        )


class YandexFileParser(BaseFileParser):
    """Парсер файлов Яндекс Маркета."""

    @property
    def platform(self) -> str:
        return "yandex"

    @property
    def supported_formats(self) -> list[str]:
        return ["csv", "xlsx"]

    def parse(self, file_content: bytes, file_type: str) -> ParseResult:
        # Используем тот же парсер, что и для WB (плоские файлы)
        wb_parser = WBFileParser()
        return wb_parser._parse_flat(file_content, file_type)
