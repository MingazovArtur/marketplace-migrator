"""Билдер простой книги для площадок без эталонного шаблона (WB, Магнит и др.)."""

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from services.xlsx_generator.columns import HEADER_FONT, RED_FILL
from services.xlsx_generator.common import (
    _add_dict_sheet,
    _fill_dict_sheet,
    _norm,
    _unique_articles,
)
from services.xlsx_generator.ozon import _cell_value


def build_simple_workbook(platform: str, products: list, spec: dict | None) -> Workbook:
    _unique_articles(products)
    wb = Workbook()
    ws = wb.active
    ws.title = "Товары"

    columns = [
        {"header": "Артикул", "key": "article", "required": True, "type": "text", "values": None, "multi": False},
        {"header": "Название", "key": "name", "required": True, "type": "text", "values": None, "multi": False},
        {"header": "Цена", "key": "price", "required": True, "type": "number", "values": None, "multi": False},
        {"header": "Категория", "key": "category", "required": False, "type": "text", "values": None, "multi": False},
        {"header": "Штрихкод", "key": "barcode", "required": False, "type": "text", "values": None, "multi": True},
    ]
    for a in (spec or {}).get("attributes") or []:
        columns.append(
            {
                "header": a["name"],
                "key": f"attr:{_norm(a['name'])}",
                "required": bool(a.get("required")),
                "type": a.get("type", "text"),
                "values": a.get("values"),
                "multi": a.get("type") == "multiselect",
            }
        )

    used_dicts = {}
    for idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=idx, value=col["header"] + ("*" if col["required"] else ""))
        cell.font = HEADER_FONT
        if col["required"]:
            cell.fill = RED_FILL
        if col["values"]:
            rng = f"{get_column_letter(idx)}2:{get_column_letter(idx)}{len(products) + 51}"
            if len(col["values"]) <= 8:
                dv = DataValidation(
                    type="list",
                    formula1='"' + ",".join(str(v) for v in col["values"]) + '"',
                    allow_blank=True,
                )
                ws.add_data_validation(dv)
                dv.add(rng)
            else:
                title = _add_dict_sheet(wb, col["header"], used_dicts)
                n = _fill_dict_sheet(wb, title, col["values"])
                dv = DataValidation(
                    type="list", formula1=f"'{title}'!$A$1:$A${n}", allow_blank=True
                )
                ws.add_data_validation(dv)
                dv.add(rng)

    for r, product in enumerate(products, start=2):
        attr_map = {
            _norm(a.get("name")): a.get("value")
            for a in (product.get("attributes") or [])
            if a.get("name")
        }
        for idx, col in enumerate(columns, start=1):
            value = _cell_value(product, col, attr_map, row_num=r - 1)
            if value is None or value == "":
                continue
            ws.cell(row=r, column=idx, value=value)

    return wb


# ========== Оркестратор ==========
