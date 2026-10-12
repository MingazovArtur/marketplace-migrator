"""
Извлечение вариаций товара из строк файла импорта.
Каждая строка группы (SKU) становится вариацией товара.
"""



def _clean(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(" ", "").replace(",", ".").replace("₽", ""))
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).replace(" ", "")))
    except (TypeError, ValueError):
        return None


def extract_variants(rows: list[dict]) -> list[dict]:
    """
    Принимает список сырых строк одной карточки (группы) и возвращает вариации.
    Поддерживает русские и английские названия колонок.
    """
    variants = []
    seen = set()

    for row in rows:
        sku = _clean(
            row.get("ШК")
            or row.get("sku")
            or row.get("SKU")
            or row.get("Артикул")
            or row.get("Артикул продавца")
        )
        if not sku or sku in seen:
            continue
        seen.add(sku)

        variants.append(
            {
                "sku": sku,
                "size": _clean(
                    row.get("Размер") or row.get("size") or row.get("Российский размер")
                ),
                "color": _clean(row.get("Цвет") or row.get("color")),
                "price": _to_float(row.get("Цена") or row.get("price") or row.get("Цена, руб")),
                "stock": _to_int(row.get("Остаток") or row.get("stock") or row.get("Количество")),
                "sort_order": len(variants),
            }
        )

    return variants
