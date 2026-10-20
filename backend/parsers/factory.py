"""
Фабрика парсеров файлов маркетплейсов.
Выбирает нужный парсер по названию площадки.
"""
import logging
from typing import Dict, Any
from .base import BaseFileParser, ParseResult
from .ozon import OzonFileParser
from .magnit import MagnitFileParser
from .wildberries import WBFileParser
from .yandex import YandexFileParser

logger = logging.getLogger(__name__)


class GenericMarketplaceParser(BaseFileParser):
    """Универсальный парсер для новых площадок (Мегамаркет, Poizon, Холодильник.ру, Страна.маркет, UDS)."""
    supported_formats = ["xlsx", "csv", "yml"]

    def parse(self, file_content: bytes, file_type: str) -> ParseResult:
        # Базовая реализация парсинга через общие утилиты или Excel/CSV reader
        import io
        import pandas as pd
        from .utils import clean_row

        result = ParseResult()
        try:
            if file_type == "csv":
                df = pd.read_csv(io.BytesIO(file_content))
            elif file_type == "xlsx":
                df = pd.read_excel(io.BytesIO(file_content))
            else:
                result.errors.append({"row": 0, "error": f"Формат {file_type} не поддерживается универсальным парсером"})
                return result

            df = df.dropna(how="all")
            result.total_rows = len(df)

            for idx, row in df.iterrows():
                row_dict = row.to_dict()
                cleaned = clean_row(row_dict)
                if not cleaned.get("name") and not cleaned.get("sku"):
                    continue
                result.products.append(cleaned)
                result.imported += 1
        except Exception as e:
            logger.error(f"Ошибка универсального парсинга: {e}")
            result.errors.append({"row": 0, "error": str(e)})

        return result


# Реестр парсеров
PARSERS = {
    "ozon": OzonFileParser,
    "magnit": MagnitFileParser,
    "wildberries": WBFileParser,
    "yandex": YandexFileParser,
    "megamarket": GenericMarketplaceParser,
    "poizon": GenericMarketplaceParser,
    "holodilnik": GenericMarketplaceParser,
    "strana": GenericMarketplaceParser,
    "uds": GenericMarketplaceParser,
}


def get_parser(platform: str) -> BaseFileParser:
    """
    Возвращает парсер для указанной площадки.
    
    Args:
        platform: Название площадки (ozon, wildberries, yandex, magnit, megamarket, poizon, holodilnik, strana, uds)
        
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


def preview_file(file_content: bytes, platform: str, file_type: str, max_rows: int = 10) -> Dict[str, Any]:
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