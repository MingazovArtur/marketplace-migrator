"""Служебные константы и конвертеры парсера Яндекс Маркета.

Вынесено без изменений из монолита parsers/yandex.py (Р24): маркеры
служебных строк шаблона (строки 3-4: подсказки и пример Makita),
перевод единиц из шаблона (см→мм, кг→г) и парсер колонки
«Характеристики товара» формата 'Имя|Значение[|ед.]'.
"""

# Маркеры служебных строк и строки-примера Яндекс Маркета (строки 3 и 4)
YANDEX_SKIP_MARKERS = (
    "значение поля выгружено",
    "заполняется автоматически",
    "уникальный идентификатор товара, для которого",
    "по схеме: тип товара + бренд",
    "ссылка на изображение товара. можно указать",
    "не более 6000 символов",
    "это пример с заполненными полями",
    "укажите свой товар или удалите строку",
    "дрель makita 6413 безударная",
    "http://example-shop.ru/",
    "https://example.com/scheme.pdf",
)


def _cm_to_mm(val_str: str) -> int | None:
    """Переводит сантиметры из шаблона Яндекса (65.55) в миллиметры (656)."""
    if not val_str:
        return None
    try:
        cm = float(str(val_str).replace(",", ".").replace(" ", ""))
        return int(round(cm * 10)) if cm > 0 else None
    except (ValueError, TypeError):
        return None


def _kg_to_grams(val_str: str) -> int | None:
    """Переводит килограммы из шаблона Яндекса (1.001) в граммы (1001)."""
    if not val_str:
        return None
    try:
        kg = float(str(val_str).replace(",", ".").replace(" ", ""))
        return int(round(kg * 1000)) if kg > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_yandex_characteristics(raw_str: str) -> list[dict[str, str]]:
    """
    Парсит колонку «Характеристики товара» формата Яндекс Маркета:
      'Цвет|Красный;Длина|100|см' -> [{'name': 'Цвет', 'value': 'Красный'}, {'name': 'Длина', 'value': '100 см'}]
    """
    if not raw_str:
        return []
    attrs: list[dict[str, str]] = []
    for item in str(raw_str).split(";"):
        item = item.strip()
        if not item or "|" not in item:
            continue
        parts = [p.strip() for p in item.split("|") if p.strip()]
        if len(parts) >= 2:
            name = parts[0]
            value = f"{parts[1]} {parts[2]}".strip() if len(parts) >= 3 else parts[1]
            attrs.append({"name": name, "value": value})
    return attrs
