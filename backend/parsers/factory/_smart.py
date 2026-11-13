"""Универсальный парсер «умных» шаблонов (Мегамаркет, Холодильник.ру, AliExpress).

Вынесено без изменений из монолита parsers/factory.py (Р25): нормализация
заголовков (_norm_col) и SmartMarketplaceParser — распознавание
многострочных шапок официальных шаблонов площадок, подбор лучших
SKU/название/цена колонок по нормализованным ключам.
"""

import logging
import re
from typing import Any

from parsers.base import BaseFileParser, ParseResult
from parsers.tables import ExcelBook, read_csv_table

logger = logging.getLogger(__name__)


def _norm_col(name: Any) -> str:
    return re.sub(r"[^a-zа-я0-9]", "", str(name or "").lower().rstrip("*"))


class SmartMarketplaceParser(BaseFileParser):
    """
    Парсер XLSX/CSV файлов для Мегамаркета, Холодильник.ру и AliExpress.
    Распознаёт многострочные шапки официальных шаблонов площадок.
    """

    supported_formats = ["xlsx", "csv", "yml"]

    # Порядок важен: сначала специфичные SKU-колонки площадок, затем модель/SPU.
    # Для AliExpress-вариаций это гарантирует Артикул (seller SKU ID) вместо
    # Модели (seller SPU ID), одинаковой у всех вариаций.
    SKU_KEYS = (
        "кодтоварапродавцаofferid",
        "кодтоварапродавца",
        "артикулштрихкодsellerskuid",
        "артикулsellerskuid",
        "sellerskuid",
        "вашsku",
        "артикулпродавца",
        "артикулsku",
        "артикул",
        "offerid",
        "модельsellerspuid",
        "sellerspuid",
        "sku",
    )
    NAME_KEYS = {
        "названиетоварапоформулетиптоварабрендмодельартикул",
        "названиетовара",
        "наименованиетовара",
        "наименование",
        "название",
        "title",
    }
    PRICE_KEYS = {
        "цена",
        "ценаруб",
        "ценасучетомскидок",
        "стоимость",
        "предельнаяценабезакцийруб",
        "price",
    }
    DESC_KEYS = {"описаниетовара", "описание", "аннотация", "description"}
    BRAND_KEYS = {"бренд", "производитель", "производительбренд", "brand"}
    BARCODE_KEYS = {
        "основнойштрихкодgtin",
        "штрихкодean",
        "штрихкодean13",
        "штрихкодbarcode",
        "штрихкод",
        "баркод",
        "gtin",
        "barcode",
    }
    CATEGORY_KEYS = {"категория", "категориянамаркете", "предмет", "предметкатегория"}
    STOCK_KEYS = {"остаток", "количество", "stock"}
    PHOTO_KEYS = {
        "urlосновногофото",
        "главноефото",
        "фотоsku",
        "ссылканафото",
        "ссылкинафото",
        "ссылканаглавноефото",
        "ссылканаизображение",
        "urlкартинки",
        "фотоurl",
    }

    def _read_best_dataframe(self, file_content: bytes, file_type: str):
        if file_type == "csv":
            return read_csv_table(file_content)

        xl = ExcelBook(file_content)
        skip_sheets = (
            "инструкция",
            "описание полей",
            "справочник",
            "правила",
            "требования",
            "видео",
            "readme",
            "help",
        )
        sheet_name = xl.sheet_names[0]
        for candidate in ("Шаблон", "Список товаров", "Товары", "Офферы", "Assortment", "Каталог"):
            if candidate in xl.sheet_names:
                sheet_name = candidate
                break
        else:
            for s in xl.sheet_names:
                if not any(w in s.lower() for w in skip_sheets):
                    sheet_name = s
                    break

        raw_df = xl.parse(sheet_name=sheet_name, header=None)
        header_idx = 0
        all_markers = set(self.SKU_KEYS) | self.NAME_KEYS
        for idx in range(min(10, len(raw_df))):
            row_norms = {_norm_col(v) for v in raw_df.iloc[idx].values if v is not None}
            if row_norms & all_markers:
                header_idx = idx
                break

        df = xl.parse(sheet_name=sheet_name, header=header_idx)
        return df

    def parse(self, file_content: bytes, file_type: str) -> ParseResult:
        result = ParseResult()
        try:
            df = self._read_best_dataframe(file_content, file_type)
            df = df.dropna_all()
            result.total_rows = len(df)

            norm_to_col: dict[str, str] = {}
            photo_cols: list[str] = []
            for col in df.columns:
                nc = _norm_col(col)
                if not nc:
                    continue
                norm_to_col.setdefault(nc, str(col))
                if nc in self.PHOTO_KEYS or nc.startswith("urlфото") or nc.startswith("фото"):
                    photo_cols.append(str(col))

            def _pick(row_data: dict, keys: set[str]) -> Any:
                for k in keys:
                    col_name = norm_to_col.get(k)
                    if col_name is not None:
                        val = row_data.get(col_name)
                        if val is not None and str(val).strip() != "":
                            return val
                return None

            for idx, row in df.iterrows():
                row_dict = row.to_dict()
                raw_name = _pick(row_dict, self.NAME_KEYS)
                raw_sku = _pick(row_dict, self.SKU_KEYS)

                # Пропускаем строки-подсказки под шапкой
                hint_check = f"{raw_name or ''} {raw_sku or ''}".lower()
                if any(
                    h in hint_check
                    for h in (
                        "уникальный артикул",
                        "обязательное поле",
                        "может быть равна артикулу",
                        "уникальный код товара",
                    )
                ):
                    continue

                if not raw_name and not raw_sku:
                    continue

                raw_price = _pick(row_dict, self.PRICE_KEYS)
                price = 0.0
                if raw_price is not None:
                    try:
                        cleaned_p = re.sub(r"[^\d.,]", "", str(raw_price)).replace(",", ".")
                        price = float(cleaned_p) if cleaned_p else 0.0
                    except ValueError:
                        price = 0.0

                photos: list[str] = []
                for pcol in photo_cols:
                    pval = row_dict.get(pcol)
                    if pval is not None and str(pval).strip():
                        for part in re.split(r"[;,\s]+", str(pval).strip()):
                            if part.startswith("http://") or part.startswith("https://"):
                                if part not in photos:
                                    photos.append(part)

                sku_str = str(raw_sku).strip() if raw_sku is not None else f"IMP-{idx + 1}"
                name_str = str(raw_name).strip() if raw_name is not None else f"Товар {sku_str}"
                desc_val = _pick(row_dict, self.DESC_KEYS)
                brand_val = _pick(row_dict, self.BRAND_KEYS)
                barcode_val = _pick(row_dict, self.BARCODE_KEYS)
                cat_val = _pick(row_dict, self.CATEGORY_KEYS)
                stock_val = _pick(row_dict, self.STOCK_KEYS)

                stock_int = 10
                if stock_val is not None:
                    try:
                        stock_int = int(float(str(stock_val).replace(",", ".")))
                    except ValueError:
                        stock_int = 10

                product = {
                    "external_id": sku_str,
                    "sku": sku_str,
                    "name": name_str,
                    "price": price,
                    "description": str(desc_val).strip() if desc_val is not None else "",
                    "brand": str(brand_val).strip() if brand_val is not None else "",
                    "barcode": str(barcode_val).strip() if barcode_val is not None else "",
                    "category": str(cat_val).strip() if cat_val is not None else "",
                    "stock": stock_int,
                    "photos": photos,
                }
                result.products.append(product)
                result.imported += 1

        except Exception as e:
            logger.error(f"Ошибка парсинга файла: {e}")
            result.errors.append({"row": 0, "error": str(e)})

        return result
