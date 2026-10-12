"""
Утилиты для работы с платформами.
Единое место для функции detect_platform (используется роутерами и задачами).
"""



def detect_platform(source_str: str) -> str | None:
    """
    Определяет платформу из строки source.

    Args:
        source_str: строка с названием платформы
                    (например, "Ozon (тест)", "Ozon → Wildberries",
                     "Магнит Маркет (файл)", "KazanExpress")

    Returns:
        'ozon', 'wildberries', 'yandex', 'magnit' или None
    """
    if not source_str:
        return None

    s = source_str.lower()

    # Если есть стрелка → берём последнюю часть (целевая платформа)
    if "→" in s:
        last = s.split("→")[-1].strip()
        if "ozon" in last:
            return "ozon"
        if "wildberries" in last or "wb" in last:
            return "wildberries"
        if "яндекс" in last or "yandex" in last:
            return "yandex"
        if "магнит" in last or "magnit" in last or "kazan" in last:
            return "magnit"

    # Иначе ищем во всей строке
    if "ozon" in s:
        return "ozon"
    if "wildberries" in s or "wb" in s:
        return "wildberries"
    if "яндекс" in s or "yandex" in s:
        return "yandex"
    if "магнит" in s or "magnit" in s or "kazan" in s:
        return "magnit"

    return None
