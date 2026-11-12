"""Публичные функции строк AliExpress: произвольные характеристики и плоские строки."""

from services.template_filler import (
    _build_enum_fix,
    _expand_products_for_platform,
    _norm,
    _row_values,
)
from services.xlsx_generator.aliexpress._layout import (
    AE_MAIN_COLUMNS,
    AE_SKU_COLUMNS,
    AE_STANDARD_NORMS,
    CUSTOM_ATTR_COUNT,
)


def aliexpress_custom_attr_names(products: list) -> list[str]:
    """
    До 5 произвольных характеристик продавца: названия атрибутов товаров,
    которых нет среди стандартных колонок шаблона.
    """
    collected: list[str] = []
    seen: set[str] = set()
    for p in products:
        for a in p.get("attributes") or []:
            name = (a.get("name") or "").strip()
            norm = _norm(name)
            if name and norm and norm not in AE_STANDARD_NORMS and norm not in seen:
                seen.add(norm)
                collected.append(name)
                if len(collected) >= CUSTOM_ATTR_COUNT:
                    return collected
    return collected


def aliexpress_flat_rows(products: list, spec: dict | None = None) -> list[dict]:
    """
    Плоские строки (заголовок → значение) для предпросмотра выгрузки.
    Вариации разворачиваются так же, как в итоговом файле.
    """
    expanded = _expand_products_for_platform(products, "aliexpress")
    enum_fix = _build_enum_fix(spec)
    custom_names = aliexpress_custom_attr_names(products)

    rows: list[dict] = []
    for i, p in enumerate(expanded, start=1):
        values = _row_values(p, i, enum_fix, platform="aliexpress")
        row: dict = {}
        for header, _req, _hint, key in AE_MAIN_COLUMNS:
            row[header] = values.get(key)
        for name in custom_names:
            row[name] = values.get(_norm(name))
        for header, _req, _hint, key in AE_SKU_COLUMNS:
            row[header] = values.get(key)
        rows.append(row)
    return rows
