"""
Валидатор товаров по спекам площадок (перед генерацией XLSX).

Эталон Ozon — реальные XLS-шаблоны от 23.09.2026
(«Адаптер для зарядки электромобиля», «Бабочка»):
  Обязательные базовые поля (со '*' и маркером «Обязательное поле»):
    Артикул, Предельная цена без акций, НДС %, ТН ВЭД коды ЕАЭС,
    Вес/Ширина/Высота/Длина упаковки, Ссылка на главное фото,
    + обязательные атрибуты категории (Бренд, Тип, Нужен код маркировки и т.д.)
  НЕ обязательное в файле: Штрихкод (Ozon генерирует сам) → warning.

ВАЖНО (v3 — согласование с XLS-шаблоном + агрессивная нормализация):
  Блокируют экспорт (severity=error) ТОЛЬКО 13 канонических колонок шаблона.
  Прочие атрибуты спека с is_required=true (Цвет товара, Пол, Российский размер…)
  дают severity=warning — XLS-шаблон пропускает файл без них, Ozon может
  попросить дозаполнить в кабинете.

  Нормализация имён атрибутов: убираем все символы, кроме букв и цифр, приводим
  к нижнему регистру. Это гарантирует, что «Название модели (для объединения в
  одну карточку)» и «Названиемоделидляобъединенияводнукарточку» считаются
  ОДНИМ И ТЕМ ЖЕ каноном.

  Синонимы имён атрибутов (в разных спеках Ozon называет их по-разному):
    «Бренд»                  <-> «Бренд в одежде и обуви»
    «Название модели (для    <-> «Объединить на одной карточке»
       объединения в одну
       карточку)»            <-> «Название модели»
    «Тип», «Нужен код маркировки» — прямое совпадение.

Правила из platform_category_specs:
- значения из словарей (регистр: warning — генератор исправит сам;
  значения нет в словаре вовсе: error — но только если атрибут в каноне)
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
from collections import Counter
from typing import Optional

# Подакцизные товары (из официальной документации Ozon)
EXCISABLE_CATEGORIES = {
    "сахаросодержащие напитки", "моторные масла", "безалкогольное пиво",
}

HASHTAG_RE = re.compile(r"^#[A-Za-zА-Яа-яЁё0-9_]{1,30}$")
OKPD_RE = re.compile(r"^\d{4,11}$")
# Ozon принимает только jpg/jpeg/png и Яндекс.Диск (по документации)
VALID_PHOTO_DOMAINS = {"yadi.sk", "disk.yandex.ru", "disk.yandex.com"}
VALID_PHOTO_EXT = (".jpg", ".jpeg", ".png")


# ==================== Агрессивная нормализация имён ====================
# Убираем ВСЁ кроме букв и цифр, приводим к нижнему регистру.
# Это позволяет распознавать «Название модели (для объединения в одну карточку)»
# и «Названиемоделидляобъединенияводнукарточку» как ОДИН канон.

def _norm_name(s: str) -> str:
    """Нормализация имени атрибута: только буквы+цифры в нижнем регистре."""
    return re.sub(r"[^a-zа-я0-9]", "", (s or "").lower())


# ==================== Канон обязательных атрибутов XLS-шаблона Ozon ====================
# Ключ — канон, значения — все возможные имена из спеков (нормализованные)
TEMPLATE_REQUIRED_ATTRS_RAW = {
    "brand": [
        "Бренд",
        "Бренд в одежде и обуви",
        "Брендодеждыиобуви",
    ],
    "model": [
        "Название модели",
        "Название модели (для объединения в одну карточку)",
        "Объединить на одной карточке",
        "Объединить в одну карточку",
        "Модель",
    ],
    "type": [
        "Тип",
    ],
    "marking": [
        "Нужен код маркировки",
        "Код маркировки",
        "Маркировка",
    ],
}

# Обратный индекс: нормализованное имя спека -> канон
_SYNONYM_INDEX = {
    _norm_name(syn): canon
    for canon, syns in TEMPLATE_REQUIRED_ATTRS_RAW.items()
    for syn in syns
}

CANON_LABELS = {
    "brand":   "Бренд",
    "model":   "Название модели (для объединения в одну карточку)",
    "type":    "Тип",
    "marking": "Нужен код маркировки",
}

# Порядок для чек-листа на фронте (канонические 13 полей шаблона Ozon)
OZON_TEMPLATE_REQUIRED_ORDER = [
    "Артикул", "Предельная цена без акций, руб.", "НДС, %", "ТН ВЭД коды ЕАЭС",
    "Вес в упаковке, г", "Ширина упаковки, мм", "Высота упаковки, мм", "Длина упаковки, мм",
    "Ссылка на главное фото", "Бренд",
    "Название модели (для объединения в одну карточку)",
    "Тип", "Нужен код маркировки",
]


def _is_canon_attr(name: str) -> Optional[str]:
    """Вернуть канон атрибута, если он входит в обязательные 13 полей шаблона."""
    return _SYNONYM_INDEX.get(_norm_name(name))


# ==================== Базовые поля Ozon ====================

def _validate_ozon_base(product: dict, issues: list):
    """Проверка базовых колонок шаблона Ozon (эталон 23.09.2026)."""

    # Артикул: генератор подставит fallback, но явный SKU предпочтителен
    if not (product.get("sku") or product.get("external_id")):
        issues.append({
            "field": "article",
            "message": "Артикул* не указан — будет подставлен внутренний ID",
            "severity": "warning",
        })

    # Предельная цена без акций, руб.*
    price = product.get("price")
    try:
        price_val = float(price) if price is not None else 0.0
    except (TypeError, ValueError):
        issues.append({
            "field": "price",
            "message": f"Некорректный формат цены: {price}",
            "severity": "error",
        })
        price_val = 0.0

    if price_val <= 0:
        issues.append({
            "field": "price",
            "message": "Предельная цена без акций, руб.* не указана или ≤ 0 (обязательное поле)",
            "severity": "error",
        })

    # Зачёркнутая цена: должна быть выше предельной
    strike = product.get("strike_price")
    if strike and price_val > 0:
        try:
            if float(strike) <= price_val:
                issues.append({
                    "field": "strike_price",
                    "message": "Зачёркнутая цена должна быть выше предельной цены",
                    "severity": "error",
                })
        except (TypeError, ValueError):
            issues.append({
                "field": "strike_price",
                "message": f"Некорректный формат зачёркнутой цены: {strike}",
                "severity": "warning",
            })

    # НДС, %*
    vat = product.get("vat_rate")
    if not vat:
        issues.append({
            "field": "vat_rate",
            "message": "НДС, %* не указан — поле обязательное в шаблоне Ozon",
            "severity": "error",
        })
    elif str(vat) not in ("none", "22", "10", "7", "5", "0"):
        issues.append({
            "field": "vat_rate",
            "message": f"Некорректное значение НДС: {vat} (допустимо: none, 22, 10, 7, 5)",
            "severity": "error",
        })

    # ТН ВЭД коды ЕАЭС* — обязательны во всех категориях (эталон 23.09.2026)
    okpd = product.get("okpd_code")
    if not okpd:
        issues.append({
            "field": "okpd_code",
            "message": "ТН ВЭД коды ЕАЭС* не указан — поле обязательное в шаблоне Ozon",
            "severity": "error",
        })
    elif not OKPD_RE.match(str(okpd).replace(".", "").replace("-", "").strip()):
        issues.append({
            "field": "okpd_code",
            "message": f"ТН ВЭД код «{okpd}» имеет нестандартный формат (ожидается 4-11 цифр)",
            "severity": "warning",
        })

    # Габариты упаковки (4 обязательных поля)
    dims = {
        "package_weight_grams": "Вес в упаковке, г",
        "package_width_mm":    "Ширина упаковки, мм",
        "package_height_mm":   "Высота упаковки, мм",
        "package_length_mm":   "Длина упаковки, мм",
    }
    missing_dims = [label for key, label in dims.items() if not product.get(key)]
    if missing_dims:
        issues.append({
            "field": "dimensions",
            "message": f"Не заполнены обязательные габариты*: {', '.join(missing_dims)}",
            "severity": "error",
        })

    # Ссылка на главное фото*
    photos = product.get("photos") or []
    if not photos:
        issues.append({
            "field": "main_photo",
            "message": "Нет ссылки на главное фото* — поле обязательное в шаблоне Ozon",
            "severity": "error",
        })
    else:
        main_url = str(photos[0]).lower().strip()
        if not _is_valid_photo_url(main_url):
            issues.append({
                "field": "main_photo",
                "message": "Ссылка на главное фото должна вести напрямую на JPG/JPEG/PNG "
                           "или быть ссылкой на Яндекс.Диск",
                "severity": "warning",
            })

    # Штрихкод: в шаблоне НЕ помечен обязательным (Ozon генерирует сам)
    if not product.get("barcode"):
        issues.append({
            "field": "barcode",
            "message": "Штрихкод не указан — Ozon сгенерирует его автоматически, "
                       "но для FBO-приёмки и компенсаций при утере лучше свой",
            "severity": "warning",
        })


def _is_valid_photo_url(url: str) -> bool:
    """
    Ozon принимает:
      - прямые ссылки на .jpg / .jpeg / .png
      - ссылки на Яндекс.Диск (yadi.sk, disk.yandex.ru)
    НЕ принимает: Google Drive, Dropbox, imgur с HTML-страницей, и т.д.
    """
    if not url.startswith(("http://", "https://")):
        return False
    for domain in VALID_PHOTO_DOMAINS:
        if domain in url:
            return True
    return url.endswith(VALID_PHOTO_EXT)


# ==================== Атрибуты категории (спек) ====================

def _validate_attributes(product: dict, spec: dict, issues: list):
    """
    Валидация атрибутов по спеку.
    v3: агрессивная нормализация имён + канон проверяется ОДИН раз в конце.
    """
    attributes = spec.get("attributes") or []

    # ✅ Ключи product_attrs — нормализованные (без пробелов и пунктуации)
    product_attrs = {
        _norm_name(a.get("name")): (a.get("value") or "")
        for a in (product.get("attributes") or [])
        if a.get("name")
    }

    # Какие каноны уже заполнены (учитывая синонимы и нормализацию)
    filled_canons = set()
    for norm_name, val in product_attrs.items():
        canon = _SYNONYM_INDEX.get(norm_name)
        if canon and str(val).strip():
            filled_canons.add(canon)

    for attr_spec in attributes:
        name = attr_spec.get("name") or ""
        name_norm = _norm_name(name)
        value = product_attrs.get(name_norm, "")
        is_multi = attr_spec.get("type") == "multiselect"
        allowed = attr_spec.get("values") or []
        allowed_lower = {str(v).strip().lower() for v in allowed}

        canon = _is_canon_attr(name)            # None или 'brand'/'model'/'type'/'marking'
        is_spec_required = bool(attr_spec.get("required"))

        # ---------- Пустое значение ----------
        if not value.strip():
            # Канонические атрибуты (Бренд/Модель/Тип/Маркировка) проверяются ОДИН раз
            # внизу функции через filled_canons. Пустой СИНОНИМ (например «Модель» при
            # заполненном «Объединить на одной карточке») ошибкой НЕ считается.
            if not canon and is_spec_required:
                issues.append({
                    "field": f"attr:{name}",
                    "message": f"Атрибут «{name}» помечен required в API-спеке, "
                               f"но в XLS-шаблоне Ozon не обязателен — рекомендуем заполнить",
                    "severity": "warning",
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
                    "severity": "error" if canon else "warning",
                })
        else:
            parts = [value.strip()]

        # ---------- Значения из словаря ----------
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
                    continue

                # ✅ КОЛОНКА «Название модели (для объединения в одну карточку)*» в XLS-шаблоне
                # принимает СВОБОДНЫЙ текст (селлеры подставляют название товара/артикул).
                # Словарь API-атрибута «Модель» к этой колонке НЕ применяется → только warning.
                if canon == "model":
                    issues.append({
                        "field": f"attr:{name}",
                        "message": f"«{name}»: значение «{p}» не из словаря API, но колонка "
                                   f"XLS-шаблона принимает свободный текст — будет записано как есть",
                        "severity": "warning",
                    })
                elif attr_spec.get("type") in ("select", "multiselect"):
                    # Словарные колонки шаблона (Бренд, Тип, Маркировка…) — значение обязано быть в словаре
                    issues.append({
                        "field": f"attr:{name}",
                        "message": f"«{name}»: значение «{p}» отсутствует в словаре площадки",
                        "severity": "error" if canon else "warning",
                    })
                else:
                    # Текстовые/числовые атрибуты со словарём-подсказкой — не блокируем
                    issues.append({
                        "field": f"attr:{name}",
                        "message": f"«{name}»: значение «{p}» не из словаря-подсказки",
                        "severity": "warning",
                    })

        # ---------- Числа ----------
        if attr_spec.get("type") == "number" and not attr_spec.get("allow_unit_in_value"):
            for p in parts:
                if re.search(r"[A-Za-zА-Яа-яЁё]", p):
                    issues.append({
                        "field": f"attr:{name}",
                        "message": f"«{name}»: число должно быть без единиц измерения (найдено: {p})",
                        "severity": "error" if canon else "warning",
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

    # ✅ Финальная проверка: все 4 канона из шаблона должны быть заполнены.
    # Это ОДИНСТВЕННОЕ место, где канон даёт error — защита от двойных ошибок.
    for canon, label in CANON_LABELS.items():
        if canon not in filled_canons:
            issues.append({
                "field": f"attr:{canon}",
                "message": f"Обязательный атрибут «{label}»* не заполнен (требуется XLS-шаблоном Ozon)",
                "severity": "error",
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
    Возвращает:
      {
        "total": int,
        "ready": int,                       # без ошибок
        "ready_with_warnings": int,         # без ошибок, но с предупреждениями
        "errors": int,                      # всего error-issues
        "warnings": int,                    # всего warning-issues
        "products_with_errors": int,        # сколько товаров имеют хотя бы 1 error
        "products_with_warnings": int,      # сколько товаров имеют хотя бы 1 warning
        "duplicate_articles": list[str],
        "template_required": list[str],     # канонические 13 полей шаблона (для фронта)
        "issues": list,
      }
    """
    all_issues = []

    # Проверка дублей артикулов (генератор присвоит _2, _3)
    article_counter = Counter()
    for p in products:
        art = p.get("sku") or p.get("external_id") or f"ID{p.get('id')}"
        article_counter[art] += 1
    duplicate_articles = sorted(a for a, c in article_counter.items() if c > 1)

    for product in products:
        category = product.get("mapped_category") or product.get("category") or "Без категории"
        spec = specs_by_category.get(category)
        issues = validate_product_by_spec(product, spec, platform)

        # Предупредить о дубле артикула
        art = product.get("sku") or product.get("external_id") or f"ID{product.get('id')}"
        if art in duplicate_articles:
            issues.append({
                "field": "article",
                "message": f"Артикул «{art}» дублируется — при генерации дубли получат "
                           f"суффиксы _2, _3 (правило Ozon: уникальный артикул на строку)",
                "severity": "warning",
            })

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
    products_with_warnings = sum(
        1 for item in all_issues
        if any(i["severity"] == "warning" for i in item["issues"])
    )

    # ready_with_warnings: без error, но есть хотя бы 1 warning
    products_only_warnings = sum(
        1 for item in all_issues
        if not any(i["severity"] == "error" for i in item["issues"])
        and any(i["severity"] == "warning" for i in item["issues"])
    )

    return {
        "total": len(products),
        "ready": len(products) - products_with_errors,
        "ready_with_warnings": products_only_warnings,
        "errors": errors,
        "warnings": warnings,
        "products_with_errors": products_with_errors,
        "products_with_warnings": products_with_warnings,
        "duplicate_articles": duplicate_articles[:20],
        "template_required": OZON_TEMPLATE_REQUIRED_ORDER if platform == "ozon" else [],
        "issues": all_issues,
    }