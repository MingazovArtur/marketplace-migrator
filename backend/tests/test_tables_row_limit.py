"""R30 (С-2 ревью): потолок строк в читателях таблиц (parsers/tables.py).

Лимит проверяется по ИСХОДНОМУ объёму данных до любых обрезок:
- CSV — после сборки записей, до построения прямоугольника/шапки;
- XLSX — по листу целиком до nrows-обрезки: «прогревочный» вызов с
  nrows=30 (поиск шапки в magnit/factory) не должен пропускать гигантов.

Дефолт MAX_TABLE_ROWS = 50 000 в тестах не разворачивается (генерировать
50-тысячную книгу ради одной проверки дорого) — проверяется явно малым
max_rows, сам дефолт — отдельным ассертом.
"""

import io

import pytest
from openpyxl import Workbook

from parsers.tables import MAX_TABLE_ROWS, ExcelBook, read_csv_table, read_excel_table


def _xlsx_bytes(rows: int) -> bytes:
    """Мини-книга: rows строк по 2 колонки."""
    wb = Workbook()
    ws = wb.active
    for i in range(rows):
        ws.append([f"c{i}", f"v{i}"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestCsvRowLimit:
    def test_over_limit_raises(self):
        content = "\n".join(["a,b"] + [f"{i},{i}" for i in range(10)]).encode()
        with pytest.raises(ValueError, match="превышен лимит 5"):
            read_csv_table(content, max_rows=5)

    def test_at_limit_ok(self):
        # шапка + 4 строки данных = 5 записей — не превышение
        content = "\n".join(["a,b"] + [f"{i},{i}" for i in range(4)]).encode()
        table = read_csv_table(content, max_rows=5)
        assert len(table) == 4

    def test_none_disables_limit(self):
        content = "\n".join(["a,b"] + [f"{i},{i}" for i in range(30)]).encode()
        table = read_csv_table(content, max_rows=None)
        assert len(table) == 30


class TestExcelRowLimit:
    def test_over_limit_raises_before_nrows(self):
        # 8 строк > лимита 3 — отклоняется даже с nrows=30 в аргументах
        book = ExcelBook(_xlsx_bytes(8))
        with pytest.raises(ValueError, match="превышен лимит 3"):
            book.parse(max_rows=3, nrows=30, header=None)

    def test_read_excel_table_param(self):
        with pytest.raises(ValueError, match="превышен лимит 4"):
            read_excel_table(_xlsx_bytes(5), max_rows=4)

    def test_at_limit_ok(self):
        table = read_excel_table(_xlsx_bytes(5), max_rows=5, header=0)
        assert len(table) == 4

    def test_default_is_50k(self):
        assert MAX_TABLE_ROWS == 50_000
