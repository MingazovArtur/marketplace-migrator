"""
Запись XLSX без pandas: строки/dict-of-columns -> листы с шапкой.

Замена pd.DataFrame + pd.ExcelWriter (pandas выкинут из рантайма —
~120 МБ pandas+numpy в прод-образе). Поведение как у pandas to_excel:
  - шапка = имена колонок, index=False;
  - порядок колонок: первое появление ключа по всем строкам;
  - None/пропущенные ключи -> пустая ячейка.
"""
from openpyxl import Workbook


def _columns_of(rows: list[dict]) -> list:
    """Колонки в порядке первого появления (как pd.DataFrame(rows))."""
    columns: list = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def _fill(ws, rows: list[dict], columns: list | None):
    cols = columns if columns is not None else _columns_of(rows)
    ws.append(list(cols))
    for row in rows:
        ws.append([row.get(c) for c in cols])
    return ws


def write_rows(wb: Workbook, sheet_name: str, rows: list[dict], columns: list | None = None):
    """ДОБАВЛЯЕТ новый лист из строк (list[dict]): шапка + значения."""
    return _fill(wb.create_sheet(sheet_name), rows, columns)


def write_columns(wb: Workbook, sheet_name: str, data: dict[str, list]):
    """ДОБАВЛЯЕТ новый лист из dict-of-columns (pd.DataFrame({...}))."""
    rows = [dict(zip(data.keys(), values)) for values in zip(*data.values())]
    return write_rows(wb, sheet_name, rows, columns=list(data.keys()))


def rows_workbook(rows: list[dict], sheet_name: str, columns: list | None = None) -> Workbook:
    """Workbook с одним листом (переиспользует дефолтный лист Workbook)."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    _fill(ws, rows, columns)
    return wb
