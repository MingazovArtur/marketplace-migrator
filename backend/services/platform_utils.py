"""
Утилиты для работы с платформами.
Единое место для функции detect_platform (используется роутерами и задачами).
"""


def _match_platform_token(text: str) -> str | None:
    """Внутренний матчер ключевых слов площадки в нижнем регистре."""
    if "ozon" in text or "озон" in text:
        return "ozon"
    if "wildberries" in text or "вайлдберриз" in text or "wb" in text:
        return "wildberries"
    if "яндекс" in text or "yandex" in text:
        return "yandex"
    if (
        "мегамаркет" in text
        or "megamarket" in text
        or "сбермегамаркет" in text
        or "sbermegamarket" in text
    ):
        return "megamarket"
    if "магнит" in text or "magnit" in text or "kazan" in text:
        return "magnit"
    if "холодильник" in text or "holodilnik" in text:
        return "holodilnik"
    if "aliexpress" in text or "алиэкспресс" in text or "алиекспресс" in text or "ali" in text:
        return "aliexpress"
    return None


def detect_platform(source_str: str) -> str | None:
    """
    Определяет платформу из строки source.

    Args:
        source_str: строка с названием платформы
                    (например, "Ozon (тест)", "Ozon → Wildberries",
                     "Магнит Маркет (файл)", "Мегамаркет",
                     "Холодильник.ру", "AliExpress")

    Returns:
        'ozon', 'wildberries', 'yandex', 'magnit', 'megamarket',
        'holodilnik', 'aliexpress' или None
    """
    if not source_str:
        return None

    s = source_str.lower()

    # Если есть стрелка → берём последнюю часть (целевая платформа)
    if "→" in s:
        last = s.split("→")[-1].strip()
        matched = _match_platform_token(last)
        if matched:
            return matched

    # Иначе ищем во всей строке
    return _match_platform_token(s)
