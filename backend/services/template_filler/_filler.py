"""Заполнение эталонного XLSX нашими товарами (каркас площадки остаётся 100% оригинальным)."""

import io
import logging

from openpyxl import load_workbook

from services.template_filler._common import _norm
from services.template_filler._sheet_scan import (
    _detect_aliexpress_custom_attr_cols,
    _detect_data_start_row,
    _find_data_sheet,
    _find_header_row,
)
from services.template_filler._storage import template_path
from services.template_filler._values import (
    _build_enum_fix,
    _expand_products_for_platform,
    _row_values,
)

logger = logging.getLogger(__name__)


def fill_official_template(
    category_name: str,
    products: list,
    spec: dict | None = None,
    platform: str = "ozon",
) -> bytes:
    """
    Открывает эталонный файл площадки (Ozon / Яндекс Маркет / WB / Магнит /
    Мегамаркет / Холодильник.ру / AliExpress),
    удаляет демонстрационные строки-примеры и заполняет нашими товарами.
    """
    pl = (platform or "ozon").lower().strip()
    path = template_path(category_name, platform=pl)
    if not path:
        raise ValueError(
            f"Эталонный шаблон для площадки '{pl}' (категория '{category_name}') не загружен"
        )

    wb = load_workbook(io.BytesIO(path.read_bytes()))
    ws = _find_data_sheet(wb)

    header_row = _find_header_row(ws) or (3 if pl == "aliexpress" else 2)
    data_start_row = _detect_data_start_row(ws, header_row, pl)

    # Для AliExpress определяем 5 колонок «Произвольные характеристики продавца»
    ae_custom_cols = (
        _detect_aliexpress_custom_attr_cols(ws, header_row) if pl == "aliexpress" else []
    )

    # Сопоставляем нормализованные заголовки с номерами столбцов
    headers: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        if col in ae_custom_cols:
            continue
        h = ws.cell(row=header_row, column=col).value
        if h:
            norm_h = _norm(str(h).rstrip("*").strip())
            if norm_h and norm_h not in headers:
                headers[norm_h] = col

    # Зачищаем примеры («Дрель Makita», демо-свитера SW01 и т.д.) ниже шапки
    if ws.max_row >= data_start_row:
        ws.delete_rows(data_start_row, ws.max_row - data_start_row + 1)

    rows_to_write = _expand_products_for_platform(products, pl)

    # Если это AliExpress и есть колонки произвольных характеристик продавца —
    # выбираем до 5 дополнительных атрибутов, которых ещё нет среди стандартных колонок шаблона,
    # и записываем их названия в header_row (строку 3), как требует документация AliExpress.
    ae_custom_attr_names: list[tuple[int, str, str]] = []
    if ae_custom_cols and rows_to_write:
        skip_norms = set(headers.keys()) | {"бренд", "цвет", "размер", "модель", "тип"}
        collected: list[tuple[str, str]] = []
        seen_norms: set[str] = set()
        for p in rows_to_write:
            for a in p.get("attributes") or []:
                aname = (a.get("name") or "").strip()
                anorm = _norm(aname)
                if aname and anorm and anorm not in skip_norms and anorm not in seen_norms:
                    seen_norms.add(anorm)
                    collected.append((aname, anorm))
                    if len(collected) >= len(ae_custom_cols):
                        break
            if len(collected) >= len(ae_custom_cols):
                break
        for col_idx, (orig_name, norm_key) in zip(ae_custom_cols, collected, strict=False):
            ws.cell(row=header_row, column=col_idx, value=orig_name)
            ae_custom_attr_names.append((col_idx, orig_name, norm_key))

    enum_fix = _build_enum_fix(spec)

    numeric_keys = {
        "весвупаковкег",
        "ширинаупаковкимм",
        "высотаупаковкимм",
        "длинаупаковкимм",
        "предельнаяценабезакцийруб",
        "зачёркнутаяценаруб",
        "зачеркнутаяценаруб",
        "вессупаковкой",
        "длинаупаковки",
        "ширинаупаковки",
        "высотаупаковки",
        "цена",
        "ценаруб",
        "ценасучетомскидок",
        "остаток",
        "зачёркнутаяцена",
        "зачеркнутаяцена",
    }
    if pl != "megamarket":
        numeric_keys |= {
            "вескг",
            "весвупаковкекг",
            "вессупаковкойкг",
            "длинасм",
            "ширинасм",
            "высотасм",
        }

    for i, product in enumerate(rows_to_write, start=1):
        values = _row_values(product, i, enum_fix, platform=pl)
        r = data_start_row + i - 1
        for key, col in headers.items():
            val = values.get(key)
            if val in (None, ""):
                continue
            if key in numeric_keys:
                try:
                    num = float(val)
                    val = int(num) if num == int(num) else num
                except (TypeError, ValueError):
                    pass
            ws.cell(row=r, column=col, value=val)

        # Заполняем значения произвольных характеристик продавца в шаблоне AliExpress
        for col_idx, _orig_name, norm_key in ae_custom_attr_names:
            cval = values.get(norm_key)
            if cval not in (None, ""):
                ws.cell(row=r, column=col_idx, value=str(cval))

    buf = io.BytesIO()
    wb.save(buf)
    logger.info(
        f"✅ Эталон [{pl}] ({path.name}): заполнено строк: {len(rows_to_write)} (со строки {data_start_row})"
    )
    return buf.getvalue()
