"""
Валидатор товаров по спекам площадок (перед генерацией XLSX).

Эталон Ozon — реальные XLS-шаблоны от 23.09.2026
(«Адаптер для зарядки электромобиля», «Бабочка»):
  Обязательные базовые поля (со '*' и маркером «Обязательное поле»):
    Артикул, Предельная цена без акций, НДС %, ТН ВЭД коды ЕАЭС,
    Вес/Ширина/Высота/Длина упаковки, Ссылка на главное фото,
    + обязательные атрибуты категории (Бренд, Тип, Нужен код маркировки и т.д.)
  НЕ обязательное в файле: Штрихкод (Ozon генерирует сам) → warning.

Правила из platform_category_specs:
- обязательные атрибуты категории
- значения из словарей (регистр: warning — генератор исправит сам;
  значения нет в словаре вовсе: error)
- множественный выбор через ";" без пробелов (warning — авто-фикс)
- лимиты множественного выбора («Ⓜ️ Не более N вариантов») — у ВСЕХ атрибутов
- числа без единиц, разделитель — точка
- JSON-атрибуты (Rich-контент, Таблица размеров) — валидный JSON

Возвращает список Issue с severity:
  - error: блокирует экспорт (площадка точно отклонит)
  - warning: потенциальная проблема или авто-исправимо при генерации
"""
import json
import re
from typing import Optional

# Подакцизные товары (из официальной документации Ozon)
EXCISABLE_CATEGORIES = {
    "сахаросодержащие напитки", "моторные масла", "безалкогольное пиво",
}

HASHTAG_RE = re.compile(r"^#[A-Za-zА-Яа-яЁё0-9_]{1,30}$")


# ==================== Базовые поля Ozon ====================

def _validate_ozon_base(product: dict, issues: list):
    """Проверка базовых колонок шаблона Ozon (эталон 23.09.2026)."""

    # Артикул: генератор подставит fallback, но явный SKU предпочтителен
    if not (product.get("sku") or product.get("external_id")):
        issues.append({
            "field": "article",
            "message": "Нет явного артикула (SKU) — будет подставлен внутренний ID",
            "severity": "warning",
        })

    # Предельная цена без акций, руб.*
    price = product.get("price")
    if price is None or float(price or 0) <= 0:
        issues.append({
            "field": "price",
            "message": "Предельная цена без акций не указана или ≤ 0 (обязательное поле)",
            "severity": "error",
        })

    # Зачёркнутая цена: должна быть выше предельной
    strike = product.get("strike_price")
    if strike and price and float(strike) <= float(price):
        issues.append({
            "field": "strike_price",
            "message": "Зачёркнутая цена должна быть выше предельной цены",
            "severity": "error",
        })

    # НДС, %*
    vat = product.get("vat_rate")
    if not vat:
        issues.append({
            "field": "vat_rate",
            "message": "НДС, % не указан — поле обязательное в шаблоне Ozon",
            "severity": "error",
        })
    elif vat not in ("none", "10", "22"):
        issues.append({
            "field": "vat_rate",
            "message": f"Некорректное значение НДС: {vat} (допустимо: none, 10, 22)",
            "severity": "error",
        })

    # ТН ВЭД коды ЕАЭС* — обязательны во всех категориях (эталон 23.09.2026)
    if not product.get("okpd_code"):
        issues.append({
            "field": "okpd_code",
            "message": "ТН ВЭД коды ЕАЭС не указан — поле обязательное в шаблоне Ozon",
            "severity": "error",
        })

    # Габариты упаковки (4 обязательных поля)
    dims = {
        "package_weight_grams": "Вес в упаковке, г",
        "package_width_mm": "Ширина упаковки, мм",
        "package_height_mm": "Высота упаковки, мм",
        "package_length_mm": "Длина упаковки, мм",
    }
    missing_dims = [label for key, label in dims.items() if not product.get(key)]
    if missing_dims:
        issues.append({
            "field": "dimensions",
            "message": f"Не заполнены обязательные габариты: {', '.join(missing_dims)}",
            "severity": "error",
        })

    # Ссылка на главное фото*
    if not (product.get("photos") or []):
        issues.append({
            "field": "main_photo",
            "message": "Нет ссылки на главное фото — поле обязательное в шаблоне Ozon",
            "severity": "error",
        })

    # Штрихкод: в шаблоне НЕ помечен обязательным (Ozon генерирует сам)
    if not product.get("barcode"):
        issues.append({
            "field": "barcode",
            "message": "Штрихкод не указан — Ozon сгенерирует его автоматически, "
                       "но для FBO-приёмки и компенсаций при утере лучше свой",
            "severity": "warning",
        })


# ==================== Атрибуты категории (спек) ====================

def _validate_attributes(product: dict, spec: dict, issues: list):
    attributes = spec.get("attributes") or []
    product_attrs = {
        (a.get("name") or "").strip().lower(): (a.get("value") or "")
        for a in (product.get("attributes") or [])
    }

    for attr_spec in attributes:
        name = attr_spec.get("name") or ""
        value = product_attrs.get(name.strip().lower(), "")
        is_multi = attr_spec.get("type") == "multiselect"
        allowed = attr_spec.get("values") or []
        allowed_lower = {str(v).strip().lower() for v in allowed}

        # ---------- Обязательность ----------
        if not value.strip():
            if attr_spec.get("required"):
                issues.append({
                    "field": f"attr:{name}",
                    "message": f"Обязательный атрибут «{name}» не заполнен",
                    "severity": "error",
                })
            continue

        # ---------- Множественный выбор: разделитель и лимит ----------
        if is_multi:
            if "; " in value or ", " in value or "," in value:
                issues.append({
                    "field": f"attr:{name}",
                    "message": f"«{name}»: значения будут приведены к формату «a;b» "
                               "(точка с запятой без пробелов) при генерации",
                    "severity": "warning",
                })
            parts = [p.strip() for p in re.split(r"[;,]", value) if p.strip()]
            max_count = attr_spec.get("max_count")
            if max_count and len(parts) > max_count:
                issues.append({
                    "field": f"attr:{name}",
                    "message": f"«{name}»: превышен лимит значений "
                               f"({len(parts)} > {max_count}) — шаблон: «Не более {max_count} вариантов»",
                    "severity": "error",
                })
        else:
            parts = [value.strip()]

        # ---------- Значения из словаря ----------
        if allowed:
            for p in parts:
                if p in allowed:
                    continue
                if p.lower() in allowed_lower:
                    issues.append({
                        "field": f"attr:{name}",
                        "message": f"«{name}»: значение «{p}» отличается регистром от словаря — "
                                   f"при генерации будет исправлено автоматически",
                        "severity": "warning",
                    })
                else:
                    issues.append({
                        "field": f"attr:{name}",
                        "message": f"«{name}»: значение «{p}» отсутствует в словаре площадки",
                        "severity": "error",
                    })

        # ---------- Числа ----------
        if attr_spec.get("type") == "number" and not attr_spec.get("allow_unit_in_value"):
            for p in parts:
                if re.search(r"[A-Za-zА-Яа-яЁё]", p):
                    issues.append({
                        "field": f"attr:{name}",
                        "message": f"«{name}»: число должно быть без единиц измерения (найдено: {p})",
                        "severity": "error",
                    })
                elif "," in p:
                    issues.append({
                        "field": f"attr:{name}",
                        "message": f"«{name}»: десятичный разделитель — точка (найдена запятая: {p})",
                        "severity": "warning",
                    })

        # ---------- JSON-атрибуты ----------
        if name.upper().endswith("JSON"):
            try:
                json.loads(value)
            except (ValueError, TypeError):
                issues.append({
                    "field": f"attr:{name}",
                    "message": f"«{name}»: невалидный JSON — Ozon отклонит карточку",
                    "severity": "error",
                })

        # ---------- Хештеги ----------
        if name.lower() == "#хештеги":
            tags = value.split()
            bad = [t for t in tags if not HASHTAG_RE.match(t)]
            if bad:
                issues.append({
                    "field": f"attr:{name}",
                    "message": f"Хештеги с нарушением формата: {', '.join(bad[:3])} "
                               "(нужно: #буквы_цифры, ≤30 символов)",
                    "severity": "warning",
                })
            if len(tags) > 30:
                issues.append({
                    "field": f"attr:{name}",
                    "message": f"Слишком много хештегов: {len(tags)} (максимум 30)",
                    "severity": "warning",
                })


# ==================== Точка входа: один товар ====================

def validate_product_by_spec(product: dict, spec: Optional[dict], platform: str = "ozon") -> list[dict]:
    """
    Валидирует товар по спеку категории.
    Возвращает список проблем: [{"field": str, "message": str, "severity": "error"|"warning"}]
    """
    issues = []

    # Базовые колонки шаблона площадки
    if platform == "ozon":
        _validate_ozon_base(product, issues)

    # Подакцизные товары
    category = (product.get("mapped_category") or product.get("category") or "").lower()
    if any(exc_cat in category for exc_cat in EXCISABLE_CATEGORIES):
        issues.append({
            "field": "excisable",
            "message": "Подакцизный товар — проверьте требования площадки по маркировке",
            "severity": "warning",
        })

    # Атрибуты категории из спека
    if not spec:
        issues.append({
            "field": "spec",
            "message": "Спека категории нет — загрузите через «Спецификации»",
            "severity": "warning",
        })
        return issues

    _validate_attributes(product, spec, issues)
    return issues


# ==================== Точка входа: список товаров ====================

def validate_products_by_specs(products: list, specs_by_category: dict, platform: str = "ozon") -> dict:
    """
    Валидирует список товаров по спекам.
    Возвращает: {"total", "ready", "errors", "warnings", "issues"}
    """
    all_issues = []

    for product in products:
        category = product.get("mapped_category") or product.get("category") or "Без категории"
        spec = specs_by_category.get(category)
        issues = validate_product_by_spec(product, spec, platform)

        if issues:
            all_issues.append({
                "product_id": product.get("id"),
                "product_name": product.get("name"),
                "category": category,
                "issues": issues,
            })

    errors = sum(
        sum(1 for i in item["issues"] if i["severity"] == "error")
        for item in all_issues
    )
    warnings = sum(
        sum(1 for i in item["issues"] if i["severity"] == "warning")
        for item in all_issues
    )
    products_with_errors = sum(
        1 for item in all_issues
        if any(i["severity"] == "error" for i in item["issues"])
    )

    return {
        "total": len(products),
        "ready": len(products) - products_with_errors,
        "errors": errors,
        "warnings": warnings,
        "issues": all_issues,
    }