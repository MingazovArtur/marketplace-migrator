"""Общие хелперы генерации XLSX: нормализация значений, словарные листы, EAN-13, уникальные артикулы."""

import re

from openpyxl import Workbook

from services.xlsx_generator.columns import BRAND_NAMES, DICT_LIMIT, G_ATTRS, G_UNION, G_VARIANT


def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Zа-яА-Я]+", "_", name).strip("_")[:40] or "category"


def _norm(name: str) -> str:
    return re.sub(r"[^a-zа-я0-9]", "", (name or "").lower())


def _strip_html(text: str) -> str:
    """Очищает описание товара от HTML-тегов (<p>, <br>, <div> и сущностей)."""
    if not text:
        return ""
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", str(text))
    cleaned = re.sub(r"(?i)</p>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">")):
        cleaned = cleaned.replace(ent, ch)
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def _match_enum_case(value: str, values: list) -> str:
    low = (value or "").strip().lower()
    for v in values or []:
        if str(v).strip().lower() == low:
            return str(v)
    return (value or "").strip()


def _normalize_multi(value: str) -> str:
    parts = re.split(r"[;,]", value or "")
    return ";".join(p.strip() for p in parts if p.strip())


def _generate_ean13(product: dict) -> str:
    """
    Генерирует валидный 13-значный штрихкод EAN-13 (префикс 200 + ID товара + контрольная цифра GS1),
    если у товара не указан собственный штрихкод (обязательно для Яндекс Маркета и WB).
    """
    pid = int(product.get("id") or 1)
    base12 = f"200{pid:09d}"[:12]
    odd_sum = sum(int(base12[i]) for i in range(0, 12, 2))
    even_sum = sum(int(base12[i]) for i in range(1, 12, 2))
    check_digit = (10 - ((odd_sum + even_sum * 3) % 10)) % 10
    return f"{base12}{check_digit}"


def _add_dict_sheet(wb: Workbook, attr_name: str, used: dict) -> str:
    base = f"dict_{_slug(attr_name)}"[:28]
    title = base
    i = 1
    while title in used:
        title = f"{base[:26]}_{i}"
        i += 1
    used[title] = True
    wb.create_sheet(title)
    return title


def _fill_dict_sheet(wb: Workbook, title: str, values: list) -> int:
    ws = wb[title]
    n = 0
    for row, v in enumerate(values[:DICT_LIMIT], start=1):
        ws.cell(row=row, column=1, value=str(v))
        n = row
    ws.sheet_state = "hidden"
    return n


def _is_brand_name(name: str) -> bool:
    return _norm(name) in {_norm(b) for b in BRAND_NAMES}


def _attr_group(attr: dict) -> str:
    name = attr.get("name") or ""
    if _is_brand_name(name) or "объедин" in name.lower():
        return G_UNION
    if (attr.get("group") or "") == "variant":
        return G_VARIANT
    return G_ATTRS


def _row3_marker(col: dict) -> str | None:
    parts = []
    if col["required"]:
        parts.append("Обязательное поле")
    elif col.get("recommended"):
        parts.append("Рекомендуем к заполнению")
    if col.get("is_brand"):
        parts.append("ϟ  Влияет на продвижение")
    if col["multi"]:
        if col.get("max_count"):
            parts.append(f"Ⓜ️ Не более {col['max_count']} вариантов")
        else:
            parts.append("Ⓜ️ Множественный выбор")
    return "\n".join(parts) if parts else None


def _unique_articles(products: list) -> None:
    seen = {}
    for p in products:
        base = p.get("sku") or p.get("external_id") or f"ID{p.get('id')}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        p["_article"] = base if count == 1 else f"{base}_{count}"


# ========== Значения ячеек Ozon ==========
