"""Билдер книги Ozon: основной лист с колонками шаблона + словарные листы-справочники."""

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from services.xlsx_generator.columns import (
    DATA_START_ROW,
    HEADER_FONT,
    OZON_BASE_COLUMNS,
    RECOMMENDED_ONLY,
    RED_FILL,
    VAT_LABELS,
)
from services.xlsx_generator.common import (
    _add_dict_sheet,
    _attr_group,
    _fill_dict_sheet,
    _is_brand_name,
    _match_enum_case,
    _norm,
    _normalize_multi,
    _row3_marker,
    _unique_articles,
)


def _cell_value(product: dict, col: dict, attr_map: dict, row_num: int):
    key = col["key"]
    if key is None:
        return None
    if key == "_row_num":
        return row_num
    if key == "article":
        return (
            product.get("_article")
            or product.get("sku")
            or product.get("external_id")
            or f"ID{product.get('id')}"
        )
    if key == "name":
        return product.get("name")
    if key == "price":
        return product.get("price")
    if key == "strike_price":
        return product.get("strike_price")
    if key == "vat_rate":
        return VAT_LABELS.get(str(product.get("vat_rate") or ""), product.get("vat_rate"))
    if key == "barcode":
        return _normalize_multi(product.get("barcode") or "") or None
    if key == "okpd_code":
        return product.get("okpd_code")
    if key in (
        "package_weight_grams",
        "package_width_mm",
        "package_height_mm",
        "package_length_mm",
    ):
        return product.get(key)
    if key == "main_photo":
        photos = product.get("photos") or []
        return photos[0] if photos else None
    if key == "extra_photos":
        photos = product.get("photos") or []
        return " ".join(photos[1:15]) if len(photos) > 1 else None
    if key == "photo_article":
        return product.get("photo_article")
    if key.startswith("attr:"):
        norm_key = key[5:]
        raw = attr_map.get(norm_key)
        if raw in (None, "") and norm_key in ("brand", "model"):
            for syn in (
                ["бренд", "брендводеждеиобуви"]
                if norm_key == "brand"
                else [
                    "названиемодели",
                    "названиемоделидляобъединенияводнукарточку",
                    "объединитьнаоднойкарточке",
                    "модель",
                ]
            ):
                if syn in attr_map and attr_map[syn] not in (None, ""):
                    raw = attr_map[syn]
                    break
        if raw in (None, "") and norm_key == "model":
            raw = product.get("name")
        if raw in (None, "") and norm_key == "marking":
            raw = "Нет"
        if norm_key in ("количествовупаковке", "количествовупаковкешт") and raw in (None, ""):
            raw = product.get("units_per_item") or 1
        if raw in (None, ""):
            return None
        if col["multi"]:
            return _normalize_multi(str(raw))
        if col.get("values"):
            return _match_enum_case(str(raw), col["values"])
        if col["type"] == "number":
            try:
                v = float(raw)
                return int(v) if v == int(v) else v
            except (TypeError, ValueError):
                return raw
        return str(raw)
    return None


# ========== Сборка резервной книги Яндекс Маркета ==========


def build_ozon_workbook(products: list, spec: dict | None) -> Workbook:
    """Шапка 1:1 с официальным шаблоном категории: база 18 колонок + атрибуты спека по порядку."""
    _unique_articles(products)

    wb = Workbook()
    ws = wb.active
    ws.title = "Шаблон"

    columns = []
    for header, key, required, ctype, hint, group in OZON_BASE_COLUMNS:
        columns.append(
            {
                "header": header,
                "key": key,
                "required": required,
                "type": ctype,
                "hint": hint,
                "group": group,
                "values": None,
                "multi": False,
                "max_count": None,
                "is_brand": False,
                "recommended": False,
            }
        )
    for col in columns:
        if col["key"] == "vat_rate":
            col["values"] = ["Не облагается", "22", "10", "7", "5"]
        elif col["key"] in ("installment", "reviews_boost"):
            col["values"] = ["Да", "Нет"]

    for a in (spec or {}).get("attributes") or []:
        name = a.get("name") or ""
        if not name:
            continue
        norm = _norm(name)
        recommended = norm in RECOMMENDED_ONLY
        required = bool(a.get("required")) and not recommended
        columns.append(
            {
                "header": name,
                "key": f"attr:{norm}",
                "required": required,
                "recommended": recommended,
                "type": a.get("type", "text"),
                "hint": a.get("description") or "",
                "group": _attr_group(a),
                "values": a.get("values"),
                "multi": a.get("type") == "multiselect",
                "max_count": a.get("max_count"),
                "is_brand": _is_brand_name(name),
            }
        )

    columns.append(
        {
            "header": "Ошибка",
            "key": None,
            "required": False,
            "recommended": False,
            "type": "text",
            "hint": "Критичная ошибка в характеристиках товара. Товар с ошибками не будет продаваться.",
            "group": "",
            "values": None,
            "multi": False,
            "max_count": None,
            "is_brand": False,
        }
    )
    columns.append(
        {
            "header": "Недочёты",
            "key": None,
            "required": False,
            "recommended": False,
            "type": "text",
            "hint": "Устаревшее или незаполненное значение в характеристиках товара.",
            "group": "",
            "values": None,
            "multi": False,
            "max_count": None,
            "is_brand": False,
        }
    )

    used_dicts = {}
    last_row = max(DATA_START_ROW + len(products) - 1, DATA_START_ROW) + 50

    for idx, col in enumerate(columns, start=1):
        letter = get_column_letter(idx)
        ws.cell(row=1, column=idx, value=col["group"] or None)

        c2 = ws.cell(row=2, column=idx, value=col["header"] + ("*" if col["required"] else ""))
        c2.font = HEADER_FONT
        if col["required"]:
            c2.fill = RED_FILL

        ws.cell(row=3, column=idx, value=_row3_marker(col))

        hint = col["hint"]
        if not hint and col["values"]:
            hint = "Выберите значение из списка. Примеры: " + "; ".join(
                str(v) for v in col["values"][:5]
            )
        ws.cell(row=4, column=idx, value=hint or None)

        if col["values"]:
            rng = f"{letter}{DATA_START_ROW}:{letter}{last_row}"
            if len(col["values"]) <= 8 and all(len(str(v)) < 20 for v in col["values"]):
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

    for r, product in enumerate(products, start=DATA_START_ROW):
        attr_map = {
            _norm(a.get("name")): a.get("value")
            for a in (product.get("attributes") or [])
            if a.get("name")
        }
        for idx, col in enumerate(columns, start=1):
            value = _cell_value(product, col, attr_map, row_num=r - DATA_START_ROW + 1)
            if value is None or value == "":
                continue
            ws.cell(row=r, column=idx, value=value)

    _build_extra_sheet(
        wb,
        "Озон.Видео",
        "Озон.Видео",
        [
            ("Артикул", True, ""),
            ("Озон.Видео: название", False, "Укажите название для видео "),
            ("Озон.Видео: ссылка", False, "Укажите ссылку на видео (MP4, MOV)."),
            ("Озон.Видео: товары на видео", False, "Перечислите SKU через запятую (не более 5)."),
        ],
    )
    _build_extra_sheet(
        wb,
        "Озон.Видеообложка",
        "Озон.Видеообложка",
        [
            ("Артикул", True, ""),
            ("Озон.Видеообложка: ссылка", False, "Укажите ссылку на видео (MP4, MOV)."),
        ],
    )
    _build_extra_sheet(
        wb,
        "Документация PDF",
        "Документация PDF",
        [
            ("Артикул", True, ""),
            ("Название файла PDF", False, ""),
            ("Документ PDF", False, "Прямая ссылка на PDF-файл."),
        ],
    )

    return wb


def _build_extra_sheet(wb: Workbook, title: str, group_name: str, cols: list):
    ws = wb.create_sheet(title)
    for idx, (name, required, hint) in enumerate(cols, start=1):
        ws.cell(row=1, column=idx, value=group_name if idx > 1 else None)
        c2 = ws.cell(row=2, column=idx, value=name + ("*" if required else ""))
        c2.font = HEADER_FONT
        if required:
            c2.fill = RED_FILL
        ws.cell(row=3, column=idx, value="Обязательное поле" if required else None)
        ws.cell(row=4, column=idx, value=hint or None)
    return ws


# ========== Сборка книг WB ==========
