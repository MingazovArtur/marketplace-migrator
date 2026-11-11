"""
Мини-таблицы поверх openpyxl/csv — замена pandas в парсерах импорта.

pandas + numpy тянули ~120 МБ в прод-образ, а парсерам нужно немного:
прочитать лист/CSV в прямоугольную таблицу, найти шапку, пройтись по
строкам. Здесь ровно эта функциональность, с сохранением поведения
pandas, на которое опираются парсеры:

  - пропущенные значения -> None (аналог NaN);
  - полностью пустые строки в хвосте xlsx отбрасываются, внутри — остаются;
  - рваные ряды дополняются до прямоугольника;
  - дубликаты имён колонок получают суффиксы ".1", ".2" (как pandas);
  - пустые поля CSV -> None; полностью пустые строки CSV пропускаются
    (аналог skip_blank_lines=True);
  - header=N: строка N — шапка, строки выше отбрасываются.

Отличие от pandas (осознанное улучшение): BOM в начале CSV-файла
(«CSV UTF-8» из Excel) больше не ломает поиск колонок — BOM срезается.
"""

import csv
import io

from openpyxl import load_workbook


def _mangle_columns(columns: list) -> list:
    """Дедупликация имён колонок с суффиксами, как в pandas: a, a.1, a.2."""
    seen: dict = {}
    result = []
    for col in columns:
        name = col if col is not None else "Unnamed"
        if name in seen:
            seen[name] += 1
            result.append(f"{name}.{seen[name]}")
        else:
            seen[name] = 0
            result.append(name)
    return result


class Row:
    """Строка таблицы: доступ по имени колонки и по позициям (values)."""

    __slots__ = ("values", "_columns")

    def __init__(self, values: list, columns: list):
        self.values = values
        self._columns = columns

    def get(self, name, default=None):
        """Значение по имени колонки (первое совпадение при дублях)."""
        try:
            return self.values[self._columns.index(name)]
        except ValueError:
            return default

    def to_dict(self) -> dict:
        return dict(zip(self._columns, self.values))


class Table:
    """Прямоугольная таблица: columns + строки (значения или None).

    Как у pandas: у строк есть исходные индексы — dropna_all и срезы iloc
    их сохраняют (парсеры используют их для номеров строк/IMP-N).
    """

    def __init__(self, columns=None, rows=None):
        self.columns = list(columns) if columns else []
        self._rows = [list(r) for r in rows] if rows else []
        self._indices = list(range(len(self._rows)))

    # --- базовые свойства ---------------------------------------------------
    @property
    def empty(self) -> bool:
        return len(self._rows) == 0 or len(self.columns) == 0

    def __len__(self) -> int:
        return len(self._rows)

    def __bool__(self) -> bool:
        # как у pandas: истинность таблицы неопределена — всегда True
        return True

    def copy(self) -> "Table":
        t = Table(self.columns, self._rows)
        t._indices = list(self._indices)
        return t

    # --- итерация ------------------------------------------------------------
    def iterrows(self):
        """(исходный индекс строки, Row) — индексы сохраняются после dropna_all/срезов."""
        for i, values in enumerate(self._rows):
            yield self._indices[i], Row(values, self.columns)

    @property
    def iloc(self):
        return _ILoc(self)

    def dropna_all(self) -> "Table":
        """Аналог df.dropna(how='all'): выкидывает строки целиком из None,
        сохраняя исходные индексы оставшихся (как pandas)."""
        kept = [
            (idx, r)
            for idx, r in zip(self._indices, self._rows)
            if any(v is not None for v in r)
        ]
        t = Table(self.columns, [r for _, r in kept])
        t._indices = [idx for idx, _ in kept]
        return t


class _ILoc:
    def __init__(self, table: Table):
        self._t = table

    def __getitem__(self, key):
        if isinstance(key, slice):
            t = Table(self._t.columns, self._t._rows[key])
            t._indices = self._t._indices[key]
            return t
        return Row(self._t._rows[key], self._t.columns)


# ---------------------------------------------------------------------------
# Чтение CSV
# ---------------------------------------------------------------------------

def read_csv_table(content: bytes) -> Table:
    """CSV -> Table. Кодировки: utf-8(-sig) -> windows-1251 -> utf-8/replace."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("windows-1251")
        except UnicodeDecodeError:
            text = content.decode("utf-8", errors="replace")

    rows = []
    for record in csv.reader(io.StringIO(text)):
        if not record:  # полностью пустая строка — как skip_blank_lines
            continue
        rows.append([f if f != "" else None for f in record])

    if not rows:
        raise ValueError("Файл пуст")

    width = max(len(r) for r in rows)
    rows = [r + [None] * (width - len(r)) for r in rows]
    columns = _mangle_columns(
        [str(c) if c is not None else f"Unnamed: {i}" for i, c in enumerate(rows[0])]
    )
    return Table(columns, rows[1:])


# ---------------------------------------------------------------------------
# Чтение XLSX
# ---------------------------------------------------------------------------

class ExcelBook:
    """Аналог pd.ExcelFile: список листов + parse() с выбором шапки."""

    def __init__(self, content: bytes):
        # не read_only: лист может читаться повторно (поиск шапки + сам парсинг)
        self._wb = load_workbook(io.BytesIO(content), data_only=True)
        self.sheet_names = list(self._wb.sheetnames)

    def parse(self, sheet_name=None, header: int | None = 0, nrows: int | None = None) -> Table:
        ws = self._wb[sheet_name] if sheet_name is not None else self._wb[self.sheet_names[0]]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]

        # пустые строки в хвосте отбрасываем (как pandas read_excel)
        while rows and all(v is None for v in rows[-1]):
            rows.pop()
        if nrows is not None:
            rows = rows[:nrows]
        if not rows:
            raise ValueError("Лист пуст")

        # прямоугольник
        width = max(len(r) for r in rows)
        rows = [r + [None] * (width - len(r)) for r in rows]

        if header is None:
            return Table(list(range(width)), rows)

        if header >= len(rows):
            raise ValueError("Строка шапки за пределами листа")

        columns = _mangle_columns(
            [c if c is not None else f"Unnamed: {i}" for i, c in enumerate(rows[header])]
        )
        return Table(columns, rows[header + 1:])


def read_excel_table(content: bytes, sheet_name=None, header: int | None = 0) -> Table:
    """XLSX -> Table одним вызовом (первый лист по умолчанию)."""
    return ExcelBook(content).parse(sheet_name=sheet_name, header=header)
