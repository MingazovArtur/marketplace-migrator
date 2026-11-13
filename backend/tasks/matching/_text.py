"""Текстовые и скалярные утилиты подбора категории.

Вынесено без изменений из монолита tasks/matching.py (Р20): нормализация
имён атрибутов (_norm_name), наивный русский стемминг для сопоставления
чисел (_stem_ru), безопасный float (_safe_float), базовый источник
импорта (_base_source — защита от накопления «A → B → B → B»).
"""

import logging
import re as _re

logger = logging.getLogger(__name__)


def _norm_name(s):
    """Нормализация имени атрибута: убираем всё кроме букв и цифр, в нижний регистр."""
    return _re.sub(r"[^a-zа-я0-9]", "", (s or "").lower())


def _stem_ru(word: str) -> str:
    """Стемминг русских окончаний для сопоставления единственного и множественного числа."""
    w = (word or "").lower().strip()
    if len(w) <= 3:
        return w
    for suffix in (
        "ами",
        "ями",
        "ев",
        "ов",
        "ей",
        "ам",
        "ям",
        "ах",
        "ях",
        "ую",
        "юю",
        "ые",
        "ие",
        "ой",
        "ий",
        "ый",
    ):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    for suffix in ("а", "я", "ы", "и", "е", "о", "у", "ю", "ь"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _safe_float(value, default: float = 0.0) -> float:
    """Безопасное преобразование в float (строки, Decimal, None → default)."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(f"⚠️ Не удалось преобразовать '{value}' в float → {default}")
        return default


def _base_source(source_value: str) -> str:
    """
    Базовый источник импорта — часть до первой стрелки « → ».
    Защита от накопления «Магнит Маркет (Файл) → Ozon → Ozon → Ozon»
    при повторных миграциях одного и того же товара.
    """
    if not source_value:
        return "неизвестно"
    return str(source_value).split(" → ")[0].strip()
