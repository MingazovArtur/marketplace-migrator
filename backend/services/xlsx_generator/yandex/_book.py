"""Сборка книги Яндекс Маркета: «Инструкция» + «Список товаров».

Вынесено без изменений из монолита services/xlsx_generator/yandex.py (Р23).
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from services.xlsx_generator.columns import (
    CELL_BORDER,
    DATA_FONT,
    GRAY_FILL,
    GROUP_FONT,
    HEADER_FONT,
    HINT_FONT,
    RED_HEADER_FONT,
    YANDEX_GROUP_MERGES,
    YANDEX_TEMPLATE_COLUMNS,
    YM_HINT_FILL,
)
from services.xlsx_generator.common import _norm, _unique_articles
from services.xlsx_generator.yandex._instruction import _populate_yandex_instruction_sheet
from services.xlsx_generator.yandex._values import _yandex_cell_value


def build_yandex_workbook(products: list, spec: dict | None = None) -> Workbook:
    """
    Резервный генератор книги Яндекс Маркета с 2 листами («Инструкция» и «Список товаров»),
    используемый, если пользователь ещё не загрузил эталонный шаблон Яндекс Маркета.
    """
    _unique_articles(products)
    wb = Workbook()

    ws_instr = wb.active
    ws_instr.title = "Инструкция"
    _populate_yandex_instruction_sheet(ws_instr)

    ws = wb.create_sheet("Список товаров")
    wrap_align = Alignment(wrap_text=True, vertical="top")
    group_align = Alignment(horizontal="left", vertical="center")

    for col_idx, (header, _key, required, is_gray, group_title, hint) in enumerate(
        YANDEX_TEMPLATE_COLUMNS, start=1
    ):
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = 24

        c1 = ws.cell(row=1, column=col_idx, value=group_title or None)
        c1.font = GROUP_FONT
        c1.alignment = group_align
        c1.border = CELL_BORDER

        c2 = ws.cell(row=2, column=col_idx, value=header)
        c2.font = RED_HEADER_FONT if required else HEADER_FONT
        c2.alignment = wrap_align
        c2.border = CELL_BORDER
        if is_gray:
            c1.fill = GRAY_FILL
            c2.fill = GRAY_FILL

        c3 = ws.cell(row=3, column=col_idx, value=hint or None)
        c3.font = HINT_FONT
        c3.alignment = wrap_align
        c3.fill = GRAY_FILL if is_gray else YM_HINT_FILL
        c3.border = CELL_BORDER

    for start_col, end_col in YANDEX_GROUP_MERGES:
        ws.merge_cells(start_row=1, start_column=start_col, end_row=1, end_column=end_col)

    ws.row_dimensions[1].height = 26
    ws.row_dimensions[2].height = 28
    ws.row_dimensions[3].height = 95

    ym_data_start = 4
    for i, product in enumerate(products):
        r = ym_data_start + i
        attr_map = {
            _norm(a.get("name")): a.get("value")
            for a in (product.get("attributes") or [])
            if a.get("name")
        }
        for col_idx, (_, key, _, is_gray, _, _) in enumerate(YANDEX_TEMPLATE_COLUMNS, start=1):
            cell = ws.cell(row=r, column=col_idx)
            cell.font = DATA_FONT
            if is_gray:
                cell.fill = GRAY_FILL
                continue
            val = _yandex_cell_value(product, key, attr_map)
            if val not in (None, ""):
                cell.value = val

    wb.active = ws
    return wb
