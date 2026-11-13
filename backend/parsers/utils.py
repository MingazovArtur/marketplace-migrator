"""
Общие утилиты для парсеров: очистка данных, нормализация.
"""
import math
import re
from typing import Any


def clean_value(value: Any) -> str:
    """Очищает значение от пробелов и приводит к строке. Пустые/NaN -> ''."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def find_column(columns: list[str], candidates: list[str]) -> str | None:
    """Ищет колонку по списку возможных названий (регистронезависимо)."""
    col_lower_map = {str(c).lower().strip(): str(c) for c in columns}

    # Точное совпадение
    for candidate in candidates:
        key = candidate.lower().strip()
        if key in col_lower_map:
            return col_lower_map[key]

    # Частичное совпадение
    for candidate in candidates:
        candidate_lower = candidate.lower().strip()
        for col_lower, col_orig in col_lower_map.items():
            if candidate_lower in col_lower:
                return col_orig

    return None


def split_photos(photo_str: str) -> list[str]:
    """Разбивает строку с фото по ';' или ',' и возвращает список ссылок."""
    if not photo_str:
        return []
    parts = re.split(r"[;,]", photo_str)
    photos = []
    for part in parts:
        part = part.strip()
        if part and (part.startswith("http://") or part.startswith("https://")):
            photos.append(part)
    return photos


def parse_price(price_str: str) -> float:
    """Парсит цену из строки: убирает пробелы, символы валют, заменяет запятую на точку."""
    if not price_str:
        return 0.0
    cleaned = (
        str(price_str)
        .replace(" ", "")
        .replace("\u00a0", "")
        .replace("₽", "")
        .replace("руб.", "")
        .replace("руб", "")
        .replace(",", ".")
    )
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_stock(stock_str: str) -> int:
    """Парсит остаток из строки."""
    if not stock_str:
        return 0
    cleaned = str(stock_str).replace(" ", "").replace(",", "")
    try:
        return int(float(cleaned))
    except ValueError:
        return 0


def clean_vat(vat_str: str) -> str:
    """Очищает НДС и приводит к стандартному формату."""
    if not vat_str:
        return "none"
    vat_str = str(vat_str).strip().lower()
    vat_map = {
        "не облагается": "none",
        "не облагается ндс": "none",
        "0%": "none",
        "0": "none",
        "5%": "5",
        "5": "5",
        "10%": "10",
        "10": "10",
        "20%": "20",
        "20": "20",
        "22%": "22",
        "22": "22",
    }
    return vat_map.get(vat_str, vat_str.replace("%", ""))


def parse_int(val_str: str) -> int | None:
    """Парсит целое число из строки (для габаритов и веса)."""
    if not val_str:
        return None
    try:
        return int(float(str(val_str).replace(",", ".").replace(" ", "")))
    except (ValueError, TypeError):
        return None


def clean_okpd(okpd_str: str) -> str | None:
    """Очищает код ТН ВЭД, оставляя только первые 10 цифр."""
    if not okpd_str:
        return None
    digits = re.sub(r"[^\d]", "", str(okpd_str))
    return digits[:10] if digits else None


# Маркерные строки, которые нужно пропускать в файлах
SERVICE_MARKERS = [
    "не менять",
    "не изменяйте",
    "---",
    "заполняйте только",
    "обязательное поле",
    "пример заполнения",
    "ознакомьтесь с требованиями",
    "блок можно не заполнять",
    "для всех вариантов товара",
    "вы можете заполнить эти поля",
    "самые популярные способы",
    "цены и акции",
]


def is_service_row(row_text: str) -> bool:
    """Проверяет, является ли строка служебной (инструкция/подсказка)."""
    return any(marker in row_text for marker in SERVICE_MARKERS)
