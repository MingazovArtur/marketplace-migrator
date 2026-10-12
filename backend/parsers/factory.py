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

# Реестр парсеров
PARSERS = {
    "ozon": OzonFileParser,
    "magnit": MagnitFileParser,
    "wildberries": WBFileParser,
    "yandex": YandexFileParser,
}


def get_parser(platform: str) -> BaseFileParser:
    """
    Возвращает парсер для указанной площадки.
    
    Args:
        platform: Название площадки (ozon, wildberries, yandex, magnit)
        
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