"""Определение категории и значений ячеек листа «Список товаров» Яндекс Маркета.

Вынесено без изменений из монолита services/xlsx_generator/yandex.py (Р23).
"""

import re

from services.xlsx_generator.common import _generate_ean13, _norm, _strip_html


def _guess_yandex_category(product: dict) -> str:
    """
    Возвращает валидное название категории для Яндекс Маркета.
    Исключает невалидное системное значение «Не указана» / «Без категории».
    """
    for field in ("mapped_category", "category"):
        raw = (product.get(field) or "").strip()
        if raw and raw.lower() not in ("не указана", "без категории", "не маппировалось", "—"):
            parts = [p.strip() for p in re.split(r"[/\\>]", raw) if p.strip()]
            return parts[-1] if parts else raw

    name_low = (product.get("name") or "").lower()
    rules = [
        (["футболк", "майк", "лонгслив"], "Футболки и майки"),
        (["плать", "сарафан"], "Платья и сарафаны"),
        (["брюк", "джинс", "штаны", "леггинс"], "Брюки"),
        (["куртк", "пуховик", "ветровк", "пальто"], "Верхняя одежда"),
        (["толстовк", "худи", "свитшот", "джемпер", "свитер"], "Толстовки, свитшоты и худи"),
        (["носки", "гольф", "колготк"], "Носки, чулки и колготки"),
        (["кроссовк", "кеды"], "Кроссовки и кеды"),
        (["ботинк", "сапог", "туфл"], "Обувь"),
        (["смартфон", "телефон"], "Мобильные телефоны"),
        (["наушник", "гарнитур"], "Наушники и Bluetooth-гарнитуры"),
        (["швабр", "ведро", "щетк"], "Инвентарь для уборки"),
        (["кружк", "чашк", "стакан", "миск", "салатник", "тарелк"], "Столовая посуда"),
        (["лампа", "светильник", "люстр"], "Освещение"),
        (["чай"], "Чай"),
        (["кофе"], "Кофе"),
        (["книг"], "Книги"),
        (["игрушк", "конструктор", "кукл"], "Игрушки"),
    ]
    for keywords, ym_cat in rules:
        if any(k in name_low for k in keywords):
            return ym_cat
    return "Товары для дома"


def _yandex_cell_value(product: dict, key: str | None, attr_map: dict):
    if not key:
        return None
    if key == "article":
        return (
            product.get("_article")
            or product.get("sku")
            or product.get("external_id")
            or f"YM-{product.get('id')}"
        )
    if key == "name":
        return product.get("name")
    if key == "photos_comma":
        photos = product.get("photos") or []
        return ", ".join(str(u) for u in photos[:30]) if photos else None
    if key == "description":
        raw_desc = product.get("description") or product.get("name") or ""
        clean_desc = _strip_html(raw_desc)
        return clean_desc[:6000] if clean_desc else product.get("name")
    if key == "category":
        return _guess_yandex_category(product)
    if key == "brand":
        raw_brand = (
            product.get("brand")
            or attr_map.get("бренд")
            or attr_map.get("брендводеждеиобуви")
            or ""
        ).strip()
        if not raw_brand or raw_brand.lower() in (
            "отсутствует бренд",
            "без бренда",
            "noname",
            "no name",
            "нет",
        ):
            return "Нет бренда"
        return raw_brand
    if key == "barcode_comma":
        bc = product.get("barcode") or attr_map.get("штрихкод") or ""
        parts = [p.strip() for p in re.split(r"[;,]", str(bc)) if p.strip()]
        if parts:
            return ", ".join(parts)
        for v in product.get("variants") or []:
            v_sku = str(v.get("sku") or "").strip()
            if v_sku.isdigit() and 8 <= len(v_sku) <= 14:
                return v_sku
        return _generate_ean13(product)
    if key == "country":
        return attr_map.get("странапроизводства") or attr_map.get("странаизготовитель") or "Россия"
    if key == "vendor_code":
        return product.get("sku") or product.get("_article")
    if key == "weight_kg":
        wg = product.get("package_weight_grams") or product.get("weight_grams")
        return round(float(wg) / 1000.0, 3) if wg else None
    if key == "length_cm":
        mm = product.get("package_length_mm")
        return round(float(mm) / 10.0, 2) if mm else None
    if key == "width_cm":
        mm = product.get("package_width_mm")
        return round(float(mm) / 10.0, 2) if mm else None
    if key == "height_cm":
        mm = product.get("package_height_mm")
        return round(float(mm) / 10.0, 2) if mm else None
    if key == "units_per_item":
        u = product.get("units_per_item")
        return int(u) if u and int(u) > 1 else None
    if key == "price":
        return product.get("price")
    if key == "strike_price":
        return product.get("strike_price")
    if key == "marking":
        m = attr_map.get("нуженкодмаркировки") or attr_map.get("маркировка")
        if m and str(m).strip().lower() == "да":
            return "Да"
        return None
    if key == "okpd_code":
        return product.get("okpd_code") or attr_map.get("тнвэдкодыеаэс") or attr_map.get("тнвэд")
    if key == "archived":
        return "Нет"
    if key == "ym_characteristics":
        skip_norms = {
            "бренд",
            "брендводеждеиобуви",
            "странапроизводства",
            "странаизготовитель",
            "нуженкодмаркировки",
            "маркировка",
            "тнвэдкодыеаэс",
            "тнвэд",
            "названиемодели",
            "названиемоделидляобъединенияводнукарточку",
            "объединитьнаоднойкарточке",
            "модель",
            "тип",
        }
        pairs = []
        for a in product.get("attributes") or []:
            aname = (a.get("name") or "").strip()
            aval = (a.get("value") or "").strip()
            if not aname or not aval or _norm(aname) in skip_norms:
                continue
            pairs.append(f"{aname}|{aval}")
        return ";".join(pairs) if pairs else None
    return None
