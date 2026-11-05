"""
Фабрика парсеров файлов маркетплейсов.
Выбирает нужный парсер по названию площадки.
"""

import io
import logging
import re
from typing import Any, Dict

import pandas as pd

from .base import BaseFileParser, ParseResult
from .magnit import MagnitFileParser
from .ozon import OzonFileParser
from .wildberries import WBFileParser
from .yandex import YandexFileParser

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

    def _read_best_dataframe(self, file_content: bytes, file_type: str) -> pd.DataFrame:
        if file_type == "csv":
            return pd.read_csv(io.BytesIO(file_content))

        xl = pd.ExcelFile(io.BytesIO(file_content), engine="openpyxl")
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
            row_norms = {_norm_col(v) for v in raw_df.iloc[idx].values if pd.notna(v)}
            if row_norms & all_markers:
                header_idx = idx
                break

        df = xl.parse(sheet_name=sheet_name, header=header_idx)
        return df

    def parse(self, file_content: bytes, file_type: str) -> ParseResult:
        result = ParseResult()
        try:
            df = self._read_best_dataframe(file_content, file_type)
            df = df.dropna(how="all")
            result.total_rows = len(df)

            norm_to_col: dict[str, str] = {}
            photo_cols: list[str] = []
            for col in df.columns:
                nc = _norm_col(col)
                if not nc:
                    continue
                norm_to_col.setdefault(nc, col)
                if nc in self.PHOTO_KEYS or nc.startswith("urlфото") or nc.startswith("фото"):
                    photo_cols.append(col)

            def _pick(row_data: dict, keys: set[str]) -> Any:
                for k in keys:
                    col_name = norm_to_col.get(k)
                    if col_name is not None:
                        val = row_data.get(col_name)
                        if pd.notna(val) and str(val).strip() != "":
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
                    if pd.notna(pval) and str(pval).strip():
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


class MegamarketFileParser(SmartMarketplaceParser):
    """Парсер файлов Мегамаркета (Excel-файл с ассортиментом)."""

    @property
    def platform(self) -> str:
        return "megamarket"


class HolodilnikFileParser(SmartMarketplaceParser):
    """Парсер файлов Холодильник.ру."""

    @property
    def platform(self) -> str:
        return "holodilnik"


class AliexpressFileParser(SmartMarketplaceParser):
    """Парсер файлов AliExpress (официальный XLSX-шаблон)."""

    @property
    def platform(self) -> str:
        return "aliexpress"


# Реестр парсеров (7 активных площадок)
PARSERS = {
    "ozon": OzonFileParser,
    "magnit": MagnitFileParser,
    "wildberries": WBFileParser,
    "yandex": YandexFileParser,
    "megamarket": MegamarketFileParser,
    "holodilnik": HolodilnikFileParser,
    "aliexpress": AliexpressFileParser,
}


def get_parser(platform: str) -> BaseFileParser:
    """
    Возвращает парсер для указанной площадки.

    Args:
        platform: Название площадки (ozon, wildberries, yandex, magnit, megamarket, holodilnik, aliexpress)

    Returns:
        Экземпляр парсера

    Raises:
        ValueError: Если парсер для площадки не найден
    """
    platform = platform.lower().strip()

    if platform not in PARSERS:
        raise ValueError(
            f"Парсер для платформы '{platform}' не реализован. "
            f"Доступные: {', '.join(PARSERS.keys())}"
        )

    return PARSERS[platform]()


def parse_file(file_content: bytes, platform: str, file_type: str) -> ParseResult:
    """
    Точка входа для парсинга файла маркетплейса.

    Args:
        file_content: Содержимое файла в байтах
        platform: Название площадки
        file_type: Тип файла (xlsx, csv, yml)

    Returns:
        ParseResult со списком товаров и ошибками
    """
    parser = get_parser(platform)

    if file_type not in parser.supported_formats:
        raise ValueError(
            f"Платформа '{platform}' не поддерживает формат '{file_type}'. "
            f"Поддерживаемые: {', '.join(parser.supported_formats)}"
        )

    return parser.parse(file_content, file_type)


def preview_file(
    file_content: bytes, platform: str, file_type: str, max_rows: int = 10
) -> Dict[str, Any]:
    """
    Возвращает превью первых строк файла для предпросмотра перед импортом.
    """
    result = parse_file(file_content, platform, file_type)

    products = result.products
    preview = products[:max_rows]
    columns = list(preview[0].keys()) if preview else []

    return {
        "columns": columns,
        "preview": preview,
        "total_estimated": result.total_rows,
        "valid_estimated": result.imported,
        "errors": result.errors,
        "warnings": result.warnings,
    }