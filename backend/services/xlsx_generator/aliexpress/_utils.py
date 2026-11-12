"""Служебные утилиты билдера AliExpress: индексы колонок, перенос текста, ячейки."""

import math

from openpyxl.utils import get_column_letter

from services.xlsx_generator.aliexpress._layout import (
    AE_MAIN_COLUMNS,
    AE_SKU_COLUMNS,
    BLOCK_ROW,
    DATA_FONT,
    HEADER_ROW,
    HINT_ROW,
)


def _column_index(header: str, sku_start: int) -> int:
    for col, (h, *_rest) in enumerate(AE_MAIN_COLUMNS, start=1):
        if h == header:
            return col
    for idx, (h, *_rest) in enumerate(AE_SKU_COLUMNS, start=sku_start):
        if h == header:
            return idx
    return 1


def _count_lines(text: str, width: float) -> int:
    """Оценка числа строк текста при переносе по заданной ширине колонки."""
    if not text:
        return 1
    # Коэффициент 0.95 — с запасом на рендер Liberation Sans / Arial в Excel и LibreOffice
    chars_per_line = max(int((width or 18) * 0.95), 8)
    lines = 0
    for part in str(text).split("\n"):
        lines += max(1, math.ceil(len(part) / chars_per_line))
    return lines


def _fit_header_heights(ws) -> None:
    """Подгоняет высоты строк блоков/подсказок/заголовков, чтобы текст не обрезался."""
    ws.row_dimensions[BLOCK_ROW].height = 32

    hint_lines = 1
    header_lines = 1
    for col in range(1, ws.max_column + 1):
        letter = get_column_letter(col)
        width = ws.column_dimensions[letter].width or 18
        hint_val = ws.cell(row=HINT_ROW, column=col).value
        if hint_val:
            hint_lines = max(hint_lines, _count_lines(str(hint_val), width))
        header_val = ws.cell(row=HEADER_ROW, column=col).value
        if header_val:
            header_lines = max(header_lines, _count_lines(str(header_val), width))
    ws.row_dimensions[HINT_ROW].height = max(34, hint_lines * 12 + 6)
    ws.row_dimensions[HEADER_ROW].height = max(18, header_lines * 14)


def _write_cell(ws, row: int, col: int, value) -> None:
    if value in (None, ""):
        return
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = DATA_FONT


def _set_width(ws, col: int, header: str) -> None:
    letter = get_column_letter(col)
    if "фото" in header.lower() or "ссылк" in header.lower():
        width = 34
    elif "seller" in header.lower() or len(header) > 24:
        width = 26
    else:
        width = 18
    ws.column_dimensions[letter].width = width
