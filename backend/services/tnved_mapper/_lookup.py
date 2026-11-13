"""Поиск и авто-подбор кодов ТН ВЭД по справочнику.

Вынесено без изменений из монолита services/tnved_mapper.py (Р11);
TNVED_DATABASE — склейка из _database.py (тот же объект, что на пакете).
Хвостовые пробелы в docstring'ах монолита почищены (на поведение
не влияет: справочник и логика поиска неизменны, см.
tests/test_tnved_mapper_split.py).
"""

from services.tnved_mapper._database import TNVED_DATABASE


def suggest_tnved(name: str, category: str = "") -> list[dict[str, str]]:
    """
    Ищет наиболее подходящий код ТН ВЭД по названию и категории товара.

    Args:
        name: Название товара (например, "Футболка мужская хлопковая черная")
        category: Категория товара (например, "Одежда / Футболки")

    Returns:
        Список словарей с найденными совпадениями, отсортированный по релевантности.
    """
    if not name:
        return []

    # Приводим к нижнему регистру для нечувствительного поиска
    search_text = f"{name} {category}".lower()

    matches = []
    for keyword, data in TNVED_DATABASE.items():
        # Проверяем, содержится ли ключевое слово в названии или категории
        if keyword in search_text:
            matches.append(
                {
                    "keyword": keyword,
                    "code": data["code"],
                    "description": data["desc"],
                    "score": len(keyword),  # Чем длиннее совпавшее слово, тем выше релевантность
                }
            )

    # Сортируем: сначала самые длинные (точные) совпадения
    matches.sort(key=lambda x: x["score"], reverse=True)

    return matches[:3]  # Возвращаем топ-3 наиболее вероятных варианта


def get_tnved_description(code: str) -> str | None:
    """Возвращает описание по точному коду ТН ВЭД."""
    for data in TNVED_DATABASE.values():
        if data["code"] == code:
            return data["desc"]
    return None


def search_tnved(query: str) -> list[dict[str, str]]:
    """
    Поиск по справочнику ТН ВЭД по произвольному запросу.

    Args:
        query: Поисковый запрос (например, "футболка" или "6109")

    Returns:
        Список найденных записей
    """
    if not query:
        return []

    query_lower = query.lower()
    results = []

    for keyword, data in TNVED_DATABASE.items():
        # Ищем по ключевому слову, коду или описанию
        if (
            query_lower in keyword
            or query_lower in data["code"]
            or query_lower in data["desc"].lower()
        ):
            results.append(
                {
                    "keyword": keyword,
                    "code": data["code"],
                    "description": data["desc"],
                }
            )

    return results[:10]  # Возвращаем топ-10 результатов
