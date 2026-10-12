"""
Пакет парсеров файлов маркетплейсов.
"""
from .factory import parse_file, preview_file, get_parser
from .base import BaseFileParser, ParseResult

__all__ = [
    "parse_file",
    "preview_file",
    "get_parser",
    "BaseFileParser",
    "ParseResult",
]