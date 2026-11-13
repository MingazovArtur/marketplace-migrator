"""Главный билдер книги AliExpress в структуре официального XLSX-шаблона."""

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from services.template_filler import (
    _build_enum_fix,
    _expand_products_for_platform,
    _norm,
    _row_values,
)
from services.xlsx_generator.aliexpress._layout import (
    AE_CUSTOM_BLOCK,
    AE_CUSTOM_HINT,
    AE_MAIN_BLOCK,
    AE_MAIN_COLUMNS,
    AE_SKU_BLOCK,
    AE_SKU_COLUMNS,
    BLOCK_FILLS,
    BLOCK_FONT,
    BLOCK_ROW,
    CUSTOM_ATTR_COUNT,
    DATA_START_ROW,
    HEADER_FONT,
    HEADER_REQUIRED_FONT,
    HEADER_ROW,
    HINT_FONT,
    HINT_ROW,
    WRAP,
)
from services.xlsx_generator.aliexpress._rows import aliexpress_custom_attr_names
from services.xlsx_generator.aliexpress._sheets import (
    _build_images_sheet,
    _build_instruction_sheet,
)
from services.xlsx_generator.aliexpress._utils import (
    _column_index,
    _fit_header_heights,
    _set_width,
    _write_cell,
)
from services.xlsx_generator.common import _add_dict_sheet, _fill_dict_sheet


def build_aliexpress_workbook(products: list, spec: dict | None = None) -> Workbook:
    """Собирает книгу в структуре официального XLSX-шаблона AliExpress."""
    expanded = _expand_products_for_platform(products, "aliexpress")
    enum_fix = _build_enum_fix(spec)
    custom_names = aliexpress_custom_attr_names(products)

    rows_values = [
        _row_values(p, i, enum_fix, platform="aliexpress")
        for i, p in enumerate(expanded, start=1)
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "Шаблон"

    n_main = len(AE_MAIN_COLUMNS)
    n_custom = CUSTOM_ATTR_COUNT
    custom_start = n_main + 1
    sku_start = custom_start + n_custom
    total_cols = sku_start + len(AE_SKU_COLUMNS) - 1
    last_row = max(DATA_START_ROW + len(rows_values) - 1, DATA_START_ROW) + 50

    # --- Строка 1: блоки ---
    ws.cell(row=BLOCK_ROW, column=1, value=AE_MAIN_BLOCK)
    ws.merge_cells(
        start_row=BLOCK_ROW, start_column=1, end_row=BLOCK_ROW, end_column=n_main
    )
    ws.cell(row=BLOCK_ROW, column=custom_start, value=AE_CUSTOM_BLOCK)
    ws.merge_cells(
        start_row=BLOCK_ROW,
        start_column=custom_start,
        end_row=BLOCK_ROW,
        end_column=custom_start + n_custom - 1,
    )
    ws.cell(row=BLOCK_ROW, column=sku_start, value=AE_SKU_BLOCK)
    ws.merge_cells(
        start_row=BLOCK_ROW,
        start_column=sku_start,
        end_row=BLOCK_ROW,
        end_column=total_cols,
    )
    for col in range(1, total_cols + 1):
        cell = ws.cell(row=BLOCK_ROW, column=col)
        block = (
            AE_MAIN_BLOCK
            if col <= n_main
            else (AE_CUSTOM_BLOCK if col < sku_start else AE_SKU_BLOCK)
        )
        cell.fill = BLOCK_FILLS[block]
        cell.font = BLOCK_FONT
        cell.alignment = WRAP

    # --- Строка 2: подсказки + строка 3: заголовки ---
    used_dicts: dict = {}
    for col, (header, required, hint, _key) in enumerate(AE_MAIN_COLUMNS, start=1):
        ws.cell(row=HINT_ROW, column=col, value=hint).font = HINT_FONT
        ws.cell(row=HINT_ROW, column=col).alignment = WRAP
        h = ws.cell(row=HEADER_ROW, column=col, value=header + ("*" if required else ""))
        h.font = HEADER_REQUIRED_FONT if required else HEADER_FONT
        h.alignment = WRAP

    for idx, name in enumerate(custom_names):
        col = custom_start + idx
        h = ws.cell(row=HEADER_ROW, column=col, value=name)
        h.font = HEADER_FONT
        h.alignment = WRAP
    for col in range(custom_start, sku_start):
        ws.cell(row=HINT_ROW, column=col, value=AE_CUSTOM_HINT).font = HINT_FONT
        ws.cell(row=HINT_ROW, column=col).alignment = WRAP

    for idx, (header, required, hint, _key) in enumerate(AE_SKU_COLUMNS, start=sku_start):
        ws.cell(row=HINT_ROW, column=idx, value=hint).font = HINT_FONT
        ws.cell(row=HINT_ROW, column=idx).alignment = WRAP
        h = ws.cell(row=HEADER_ROW, column=idx, value=header + ("*" if required else ""))
        h.font = HEADER_REQUIRED_FONT if required else HEADER_FONT
        h.alignment = WRAP

    # --- Выпадающие списки из спека (Цвет / Размер и другие совпадающие по имени) ---
    spec_values: dict[str, list] = {}
    for a in (spec or {}).get("attributes") or []:
        if a.get("name") and a.get("values"):
            spec_values.setdefault(_norm(a["name"]), a["values"])

    for header, _required, _hint, _key in AE_MAIN_COLUMNS + AE_SKU_COLUMNS:
        values = spec_values.get(_norm(header))
        if not values or len(values) < 2:
            continue
        col_idx = _column_index(header, sku_start)
        letter = get_column_letter(col_idx)
        if len(values) <= 8 and all(len(str(v)) < 20 for v in values):
            dv = DataValidation(
                type="list",
                formula1='"' + ",".join(str(v) for v in values) + '"',
                allow_blank=True,
            )
            ws.add_data_validation(dv)
            dv.add(f"{letter}{DATA_START_ROW}:{letter}{last_row}")
        else:
            title = _add_dict_sheet(wb, f"Список {header}", used_dicts)
            n = _fill_dict_sheet(wb, title, values)
            dv = DataValidation(
                type="list", formula1=f"'{title}'!$A$1:$A${n}", allow_blank=True
            )
            ws.add_data_validation(dv)
            dv.add(f"{letter}{DATA_START_ROW}:{letter}{last_row}")

    # --- Данные ---
    for r, values in enumerate(rows_values, start=DATA_START_ROW):
        for col, (_header, _req, _hint, key) in enumerate(AE_MAIN_COLUMNS, start=1):
            _write_cell(ws, r, col, values.get(key))
        for idx, name in enumerate(custom_names):
            _write_cell(ws, r, custom_start + idx, values.get(_norm(name)))
        for idx, (_header, _req, _hint, key) in enumerate(
            AE_SKU_COLUMNS, start=sku_start
        ):
            _write_cell(ws, r, idx, values.get(key))

    # --- Ширины колонок, высоты строк шапки и закрепление шапки ---
    for col, (header, _req, _hint, _key) in enumerate(AE_MAIN_COLUMNS, start=1):
        _set_width(ws, col, header)
    for col in range(custom_start, sku_start):
        _set_width(ws, col, "Произвольная характеристика")
    for col, (header, _req, _hint, _key) in enumerate(AE_SKU_COLUMNS, start=sku_start):
        _set_width(ws, col, header)
    _fit_header_heights(ws)
    ws.freeze_panes = f"A{DATA_START_ROW}"

    _build_instruction_sheet(wb)
    _build_images_sheet(wb)
    return wb
