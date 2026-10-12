"""
Фабрика парсеров файлов маркетплейсов.
Делегирует работу специализированным классам.
"""

import logging
from typing import Any

from .base import BaseFileParser
from .ozon import OzonFileParser

# В будущем здесь будут: from .magnit import MagnitFileParser и т.д.

logger = logging.getLogger(__name__)


def get_parser(platform: str) -> BaseFileParser:
    platform = platform.lower().strip()
    if platform == "ozon":
        return OzonFileParser()
    # elif platform == "magnit":
    #     return MagnitFileParser()
    else:
        raise ValueError(
            f"Парсер для платформы '{platform}' пока не реализован или используется общий плоский парсер."
        )


def parse_file(file_content: bytes, platform: str, file_type: str) -> dict[str, Any]:
    """Точка входа для парсинга файла."""
    parser = get_parser(platform)
    return parser.parse(file_content, file_type)


def preview_file(
    file_content: bytes, platform: str, file_type: str, max_rows: int = 10
) -> dict[str, Any]:
    """Возвращает превью первых строк файла."""
    result = parse_file(file_content, platform, file_type)
    products = result.get("products", [])
    preview = products[:max_rows]
    columns = list(preview[0].keys()) if preview else []

    return {
        "columns": columns,
        "preview": preview,
        "total_estimated": result.get("total_rows", len(products)),
        "valid_estimated": result.get("imported", len(products)),
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
    }
