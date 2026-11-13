"""
Пакет парсеров файлов маркетплейсов.
"""
from .base import BaseFileParser, ParseResult
from .factory import get_parser, parse_file, preview_file

__all__ = [
    "parse_file",
    "preview_file",
    "get_parser",
    "BaseFileParser",
    "ParseResult",
]
