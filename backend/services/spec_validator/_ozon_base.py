"""Базовые колонки XLS-шаблона Ozon (эталон — реальные XLS-шаблоны от
23.09.2026, «Адаптер для зарядки электромобиля», «Бабочка»).

Вынесено без изменений из монолита services/spec_validator.py (Р12).

Обязательные базовые поля (со '*' и маркером «Обязательное поле»):
    Артикул, Предельная цена без акций, НДС %, ТН ВЭД коды ЕАЭС,
    Вес/Ширина/Высота/Длина упаковки, Ссылка на главное фото,
    + обязательные атрибуты категории (Бренд, Тип, Нужен код маркировки и т.д.)
НЕ обязательное в файле: Штрихкод (Ozon генерирует сам) → warning.
"""

import re

OKPD_RE = re.compile(r"^\d{4,11}$")
# Ozon принимает только jpg/jpeg/png и Яндекс.Диск (по документации)
VALID_PHOTO_DOMAINS = {"yadi.sk", "disk.yandex.ru", "disk.yandex.com"}
VALID_PHOTO_EXT = (".jpg", ".jpeg", ".png")


# ==================== Базовые поля Ozon ====================


def _validate_ozon_base(product: dict, issues: list):
    """Проверка базовых колонок шаблона Ozon (эталон 23.09.2026)."""

    # Артикул: генератор подставит fallback, но явный SKU предпочтителен
    if not (product.get("sku") or product.get("external_id")):
        issues.append(
            {
                "field": "article",
                "message": "Артикул* не указан — будет подставлен внутренний ID",
                "severity": "warning",
            }
        )

    # Предельная цена без акций, руб.*
    price = product.get("price")
    try:
        price_val = float(price) if price is not None else 0.0
    except (TypeError, ValueError):
        issues.append(
            {
                "field": "price",
                "message": f"Некорректный формат цены: {price}",
                "severity": "error",
            }
        )
        price_val = 0.0

    if price_val <= 0:
        issues.append(
            {
                "field": "price",
                "message": "Предельная цена без акций, руб.* не указана или ≤ 0 (обязательное поле)",
                "severity": "error",
            }
        )

    # Зачёркнутая цена: должна быть выше предельной
    strike = product.get("strike_price")
    if strike and price_val > 0:
        try:
            if float(strike) <= price_val:
                issues.append(
                    {
                        "field": "strike_price",
                        "message": "Зачёркнутая цена должна быть выше предельной цены",
                        "severity": "error",
                    }
                )
        except (TypeError, ValueError):
            issues.append(
                {
                    "field": "strike_price",
                    "message": f"Некорректный формат зачёркнутой цены: {strike}",
                    "severity": "warning",
                }
            )

    # НДС, %*
    vat = product.get("vat_rate")
    if not vat:
        issues.append(
            {
                "field": "vat_rate",
                "message": "НДС, %* не указан — поле обязательное в шаблоне Ozon",
                "severity": "error",
            }
        )
    elif str(vat) not in ("none", "22", "10", "7", "5", "0"):
        issues.append(
            {
                "field": "vat_rate",
                "message": f"Некорректное значение НДС: {vat} (допустимо: none, 22, 10, 7, 5)",
                "severity": "error",
            }
        )

    # ТН ВЭД коды ЕАЭС* — обязательны во всех категориях (эталон 23.09.2026)
    okpd = product.get("okpd_code")
    if not okpd:
        issues.append(
            {
                "field": "okpd_code",
                "message": "ТН ВЭД коды ЕАЭС* не указан — поле обязательное в шаблоне Ozon",
                "severity": "error",
            }
        )
    elif not OKPD_RE.match(str(okpd).replace(".", "").replace("-", "").strip()):
        issues.append(
            {
                "field": "okpd_code",
                "message": f"ТН ВЭД код «{okpd}» имеет нестандартный формат (ожидается 4-11 цифр)",
                "severity": "warning",
            }
        )

    # Габариты упаковки (4 обязательных поля)
    dims = {
        "package_weight_grams": "Вес в упаковке, г",
        "package_width_mm": "Ширина упаковки, мм",
        "package_height_mm": "Высота упаковки, мм",
        "package_length_mm": "Длина упаковки, мм",
    }
    missing_dims = [label for key, label in dims.items() if not product.get(key)]
    if missing_dims:
        issues.append(
            {
                "field": "dimensions",
                "message": f"Не заполнены обязательные габариты*: {', '.join(missing_dims)}",
                "severity": "error",
            }
        )

    # Ссылка на главное фото*
    photos = product.get("photos") or []
    if not photos:
        issues.append(
            {
                "field": "main_photo",
                "message": "Нет ссылки на главное фото* — поле обязательное в шаблоне Ozon",
                "severity": "error",
            }
        )
    else:
        main_url = str(photos[0]).lower().strip()
        if not _is_valid_photo_url(main_url):
            issues.append(
                {
                    "field": "main_photo",
                    "message": "Ссылка на главное фото должна вести напрямую на JPG/JPEG/PNG "
                    "или быть ссылкой на Яндекс.Диск",
                    "severity": "warning",
                }
            )

    # Штрихкод: в шаблоне НЕ помечен обязательным (Ozon генерирует сам)
    if not product.get("barcode"):
        issues.append(
            {
                "field": "barcode",
                "message": "Штрихкод не указан — Ozon сгенерирует его автоматически, "
                "но для FBO-приёмки и компенсаций при утере лучше свой",
                "severity": "warning",
            }
        )


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
