"""Формирование значений строки товара для эталонных шаблонов всех 7 площадок
и разворачивание вариаций (AliExpress / Мегамаркет)."""

import re

from services.template_filler._common import (
    BRAND_SYNONYMS,
    MARKING_SYNONYMS,
    MODEL_SYNONYMS,
    VAT_LABELS,
    _format_comma_decimal,
    _generate_ean13,
    _guess_category,
    _norm,
    _normalize_multi,
    _strip_html,
)


def _row_values(
    product: dict,
    row_num: int,
    enum_fix: dict[str, dict[str, str]],
    platform: str = "ozon",
) -> dict[str, object]:
    """
    Формирует словарь значений строки товара для любой из 7 поддерживаемых площадок:
    Ozon, Wildberries, Яндекс Маркет, Магнит Маркет, Мегамаркет, Холодильник.ру, AliExpress.
    """
    photos = [str(u).strip() for u in (product.get("photos") or []) if str(u).strip()]
    attr_map = {
        _norm(a.get("name")): a.get("value")
        for a in (product.get("attributes") or [])
        if a.get("name")
    }

    raw_article = (
        product.get("_article")
        or product.get("sku")
        or product.get("external_id")
        or f"ID{product.get('id')}"
    )
    if platform == "megamarket":
        # В Мегамаркете запрещены символы # и % в Коде товара продавца
        article = re.sub(r"[#%]+", "_", str(raw_article)).strip()
    elif platform == "aliexpress":
        # В AliExpress Артикул (seller SKU ID) — не более 50 символов
        article = str(raw_article).strip()[:50]
    else:
        article = str(raw_article).strip()

    spu_id = str(product.get("_spu_id") or article)[:50]
    clean_desc = _strip_html(product.get("description") or "") or product.get("name")

    # Бренд
    raw_brand = (
        product.get("brand") or attr_map.get("бренд") or attr_map.get("брендводеждеиобуви") or ""
    ).strip()
    if not raw_brand or raw_brand.lower() in (
        "отсутствует бренд",
        "без бренда",
        "нет бренда",
        "noname",
        "no name",
    ):
        if platform == "aliexpress":
            brand_val = "NONE"
        elif platform == "megamarket":
            brand_val = "Без бренда"
        else:
            brand_val = "Нет бренда"
    else:
        brand_val = raw_brand

    # Штрихкоды (для Мегамаркета основной штрихкод GTIN не может начинаться с 2)
    raw_bc = product.get("barcode") or attr_map.get("штрихкод") or ""
    bc_parts = [p.strip() for p in re.split(r"[;,]", str(raw_bc)) if p.strip()]
    if not bc_parts and platform in (
        "yandex",
        "wildberries",
        "megamarket",
        "holodilnik",
        "aliexpress",
    ):
        for v in product.get("variants") or []:
            v_sku = str(v.get("sku") or "").strip()
            if v_sku.isdigit() and 8 <= len(v_sku) <= 14:
                bc_parts = [v_sku]
                break
        if not bc_parts:
            bc_parts = [_generate_ean13(product, prefix="460")]

    if platform == "megamarket" and bc_parts and bc_parts[0].startswith("2"):
        bc_parts[0] = _generate_ean13(product, prefix="460")

    barcode_semi = ";".join(bc_parts) if bc_parts else None
    barcode_comma = ", ".join(bc_parts) if bc_parts else None
    main_gtin = bc_parts[0] if bc_parts else _generate_ean13(product, prefix="460")

    # Вес и габариты (в граммах/мм и в кг/см)
    wg = product.get("package_weight_grams") or product.get("weight_grams")
    l_mm = product.get("package_length_mm")
    w_mm = product.get("package_width_mm")
    h_mm = product.get("package_height_mm")

    # Для AliExpress и Мегамаркета вес и габариты не могут быть равны 0
    if platform in ("aliexpress", "megamarket"):
        wg = wg or 500
        l_mm = l_mm or 200
        w_mm = w_mm or 150
        h_mm = h_mm or 100

    weight_kg = round(float(wg) / 1000.0, 2) if wg else None
    length_cm = round(float(l_mm) / 10.0, 2) if l_mm else None
    width_cm = round(float(w_mm) / 10.0, 2) if w_mm else None
    height_cm = round(float(h_mm) / 10.0, 2) if h_mm else None
    dims_slash_cm = (
        f"{length_cm}/{width_cm}/{height_cm}" if (length_cm and width_cm and height_cm) else None
    )

    okpd = product.get("okpd_code") or attr_map.get("тнвэдкодыеаэс") or attr_map.get("тнвэд")
    units = product.get("units_per_item")
    stock_val = product.get("stock") if product.get("stock") is not None else 10
    cat_val = _guess_category(product)
    vat_val = VAT_LABELS.get(
        str(product.get("vat_rate") or ""), product.get("vat_rate") or "Не облагается"
    )

    # Вариационные поля (Цвет / Размер для AliExpress и мультикарточек)
    var_color = (
        product.get("_variant_color")
        or attr_map.get("цвет")
        or attr_map.get("цветтовара")
        or "Разноцветный"
    )
    var_size = (
        product.get("_variant_size") or attr_map.get("размер") or attr_map.get("размеродежды") or ""
    )

    # Сборка колонки «Характеристики товара» для Яндекс Маркета (Имя|Значение;Имя|Значение)
    skip_ym_attrs = {
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
    ym_pairs = []
    for a in product.get("attributes") or []:
        aname = (a.get("name") or "").strip()
        aval = (a.get("value") or "").strip()
        if aname and aval and _norm(aname) not in skip_ym_attrs:
            ym_pairs.append(f"{aname}|{aval}")
    ym_characteristics = ";".join(ym_pairs) if ym_pairs else None

    values: dict[str, object] = {
        # --- Общие и Ozon ---
        "№": row_num,
        "артикул": article,
        "артикулпродавца": article,
        "артикулsku": article,
        "вашsku": article,
        "offerid": article,
        "названиетовара": product.get("name"),
        "название": product.get("name"),
        "наименование": product.get("name"),
        "наименованиетовара": product.get("name"),
        "предельнаяценабезакцийруб": product.get("price"),
        "зачёркнутаяценаруб": product.get("strike_price"),
        "зачеркнутаяценаруб": product.get("strike_price"),
        "ндс": vat_val,
        "штрихкодсерийныйномерean": barcode_semi,
        "штрихкодbarcode": barcode_semi,
        "штрихкодean13": main_gtin,
        "barcode": barcode_semi,
        "тнвэдкодыеаэс": okpd,
        "весвупаковкег": wg,
        "ширинаупаковкимм": w_mm,
        "высотаупаковкимм": h_mm,
        "длинаупаковкимм": l_mm,
        "ссылканаглавноефото": photos[0] if photos else None,
        "ссылкинадополнительныефото": " ".join(photos[1:15]) if len(photos) > 1 else None,
        "аннотация": clean_desc,
        # --- Мегамаркет (точные поля из документации и скриншота) ---
        "кодтоварапродавца": article,
        "кодтоварапродавцаofferid": article,
        "основнойштрихкодgtin": main_gtin,
        "штрихкод2": bc_parts[1] if len(bc_parts) > 1 else None,
        "штрихкод3": bc_parts[2] if len(bc_parts) > 2 else None,
        "штрихкод4": bc_parts[3] if len(bc_parts) > 3 else None,
        "штрихкод5": bc_parts[4] if len(bc_parts) > 4 else None,
        "ссылканаpdfинструкцию": attr_map.get("ссылканаpdfинструкцию") or None,
        "ссылканасертификат": attr_map.get("ссылканасертификат") or None,
        "названиетоварапоформулетиптоварабрендмодельартикул": product.get("name"),
        "urlосновногофото": photos[0] if photos else None,
        "urlфото2": photos[1] if len(photos) > 1 else None,
        "urlфото3": photos[2] if len(photos) > 2 else None,
        "urlфото4": photos[3] if len(photos) > 3 else None,
        "urlфото5": photos[4] if len(photos) > 4 else None,
        "urlфото6": photos[5] if len(photos) > 5 else None,
        "urlфото7": photos[6] if len(photos) > 6 else None,
        "urlфото8": photos[7] if len(photos) > 7 else None,
        "urlфото9": photos[8] if len(photos) > 8 else None,
        "urlфото10": photos[9] if len(photos) > 9 else None,
        # --- AliExpress (точные поля из документации и скриншотов) ---
        "модельsellerspuid": spu_id,
        "sellerspuid": spu_id,
        "артикулштрихкодsellerskuid": article,
        "артикулsellerskuid": article,
        "sellerskuid": article,
        "штрихкодean": main_gtin,
        "gtin": main_gtin,
        "главноефото": photos[0] if photos else None,
        "фотоsku": product.get("_variant_photo") or (photos[0] if photos else None),
        "цвет": var_color,
        "размер": var_size,
        "доставкаиз": "Российская Федерация",
        "названиецветавсистемепродавца": var_color,
        "названиеразмеравсистемепродавца": var_size,
        "вессупаковкой": weight_kg,
        "длинаупаковки": int(round(length_cm)) if length_cm else None,
        "ширинаупаковки": int(round(width_cm)) if width_cm else None,
        "высотаупаковки": int(round(height_cm)) if height_cm else None,
        # --- Яндекс Маркет / Холодильник.ру / Магнит ---
        "ссылканаизображение": ", ".join(photos[:30]) if photos else None,
        "ссылканафото": (
            "; ".join(photos[:15])
            if platform != "yandex"
            else (", ".join(photos[:30]) if photos else None)
        ),
        "ссылкинафото": "; ".join(photos[:15]) if photos else None,
        "фотоurl": "; ".join(photos[:10]) if photos else None,
        "urlкартинки": photos[0] if photos else None,
        "описаниетовара": clean_desc[:6000] if clean_desc else None,
        "описание": clean_desc[:6000] if clean_desc else None,
        "категориянамаркете": cat_val,
        "категория": cat_val,
        "предмет": cat_val,
        "предметкатегория": cat_val,
        "бренд": brand_val,
        "производитель": brand_val,
        "производительбренд": brand_val,
        "штрихкод": (
            barcode_comma
            if platform == "yandex"
            else (main_gtin if platform == "megamarket" else barcode_semi)
        ),
        "баркод": barcode_comma if platform == "yandex" else barcode_semi,
        "странапроизводства": attr_map.get("странапроизводства")
        or attr_map.get("странаизготовитель")
        or "Россия",
        "артикулпроизводителя": article,
        "вескг": _format_comma_decimal(weight_kg) if platform == "megamarket" else weight_kg,
        "весвупаковкекг": (
            _format_comma_decimal(weight_kg) if platform == "megamarket" else weight_kg
        ),
        "вессупаковкойкг": (
            _format_comma_decimal(weight_kg) if platform == "megamarket" else weight_kg
        ),
        "длинасм": _format_comma_decimal(length_cm) if platform == "megamarket" else length_cm,
        "длинаупаковкисм": (
            _format_comma_decimal(length_cm) if platform == "megamarket" else length_cm
        ),
        "ширинасм": _format_comma_decimal(width_cm) if platform == "megamarket" else width_cm,
        "ширинаупаковкисм": (
            _format_comma_decimal(width_cm) if platform == "megamarket" else width_cm
        ),
        "высотасм": _format_comma_decimal(height_cm) if platform == "megamarket" else height_cm,
        "высотаупаковкисм": (
            _format_comma_decimal(height_cm) if platform == "megamarket" else height_cm
        ),
        "габаритысупаковкойсм": dims_slash_cm,
        "товардоставляетсявнесколькихупаковках": int(units) if units and int(units) > 1 else None,
        "цена": product.get("price"),
        "ценаруб": product.get("price"),
        "ценасучетомскидок": product.get("price"),
        "остаток": stock_val,
        "зачёркнутаяцена": product.get("strike_price"),
        "зачеркнутаяцена": product.get("strike_price"),
        "ценадоскидки": product.get("strike_price"),
        "тнвэд": okpd,
        "характеристикитовара": ym_characteristics,
        "вархиве": "Нет",
    }

    # Атрибуты товара — по нормализованному имени колонки
    for key, val in attr_map.items():
        if val not in (None, ""):
            values.setdefault(key, val)

    # Фолбэки-синонимы канонических колонок
    for b in BRAND_SYNONYMS:
        values.setdefault(b, brand_val)
    if not any(values.get(m) for m in MODEL_SYNONYMS):
        for m in MODEL_SYNONYMS:
            values[m] = spu_id if platform == "aliexpress" else product.get("name")
    if not any(values.get(m) for m in MARKING_SYNONYMS):
        values[MARKING_SYNONYMS[0]] = "Нет"
    if not values.get("количествовупаковке") and not values.get("количествовупаковкешт") and units:
        values["количествовупаковке"] = units

    # Приведение значений к регистру словаря площадки и очистка разделителей
    for key, val in list(values.items()):
        if val in (None, "") or isinstance(val, (int, float)):
            continue
        s = str(val)
        if (
            platform in ("ozon", "megamarket")
            and (";" in s or "," in s)
            and key
            not in (
                "аннотация",
                "описание",
                "описаниетовара",
                # Названия товаров не трогаем: запятая — часть текста
                "названиетоварапоформулетиптоварабрендмодельартикул",
                "названиетовара",
                "наименованиетовара",
                "наименование",
                "название",
                "вескг",
                "весвупаковкекг",
                "вессупаковкойкг",
                "длинасм",
                "длинаупаковкисм",
                "ширинасм",
                "ширинаупаковкисм",
                "высотасм",
                "высотаупаковкисм",
            )
        ):
            s = "; ".join(p.strip() for p in re.split(r"[;,]", s) if p.strip())
            if platform == "ozon":
                s = _normalize_multi(s)
        fix = enum_fix.get(key)
        if fix:
            s = fix.get(s.strip().lower(), s)
        values[key] = s
    return values


def _build_enum_fix(spec: dict | None) -> dict[str, dict[str, str]]:
    fix: dict[str, dict[str, str]] = {}
    for a in (spec or {}).get("attributes") or []:
        vals = a.get("values") or []
        if vals:
            fix[_norm(a.get("name"))] = {str(v).strip().lower(): str(v) for v in vals}
    return fix


def _expand_products_for_platform(products: list, platform: str) -> list[dict]:
    """
    Для AliExpress и Мегамаркета: если у товара заданы вариации (`variants`),
    разворачивает их в отдельные строки с единым SPU ID (`_spu_id` / `Модель`)
    и индивидуальным SKU ID (`_article`), цветом и размером.
    """
    expanded: list[dict] = []
    seen: dict[str, int] = {}

    for p in products:
        base_sku = str(p.get("sku") or p.get("external_id") or f"ID{p.get('id')}").strip()
        seen[base_sku] = seen.get(base_sku, 0) + 1
        spu_id = base_sku if seen[base_sku] == 1 else f"{base_sku}_{seen[base_sku]}"

        variants = p.get("variants") or []
        if platform == "aliexpress" and len(variants) > 0:
            for idx, v in enumerate(variants, start=1):
                clone = dict(p)
                clone["_spu_id"] = spu_id
                v_sku = str(v.get("sku") or f"{spu_id}-{idx}").strip()
                clone["_article"] = v_sku
                clone["_variant_color"] = v.get("color") or ""
                clone["_variant_size"] = v.get("size") or v.get("name") or ""
                clone["_variant_photo"] = v.get("photo") or ""
                # Уникальный штрихкод вариации (Штрихкод / EAN — уникален для SKU)
                if v.get("barcode"):
                    clone["barcode"] = str(v["barcode"]).strip()
                if v.get("price"):
                    clone["price"] = v["price"]
                if v.get("stock") is not None:
                    clone["stock"] = v["stock"]
                expanded.append(clone)
        else:
            clone = dict(p)
            clone["_spu_id"] = spu_id
            clone["_article"] = spu_id
            expanded.append(clone)

    return expanded
