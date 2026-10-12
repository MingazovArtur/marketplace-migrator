"""
Скрипт для получения актуальных категорий с Ozon и Wildberries через API
Запуск: python backend/scripts/fetch_categories.py
"""

import json
from pathlib import Path

import requests

# Пути
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = DATA_DIR / "marketplace_categories.json"

# ============================================
# WILDBERRIES
# ============================================


def _load_local_wb_subjects() -> dict:
    """Загружает категории из локального файла, если API недоступен"""
    local_file = Path(__file__).parent.parent / "data" / "wildberries_subjects.json"
    if local_file.exists():
        with open(local_file, encoding="utf-8") as f:
            data = json.load(f)
        print(f"   ✅ Загружено {len(data)} категорий из локального файла")
        return data
    else:
        print(
            "   ❌ Локальный файл не найден! Убедитесь, что создан backend/data/wildberries_subjects.json"
        )
        return {}


def fetch_wildberries_subjects(api_key: str = "") -> dict:
    """
    Получает справочник предметов Wildberries через актуальный Content API
    Docs: https://dev.wildberries.ru/openapi/content-api#tag/Spravochniki/paths/~1content~1v2~1get~1subjects/get
    """
    print(" Получаем категории Wildberries...")

    # Актуальные endpoints из документации WB (2026)
    endpoints = []

    if api_key:
        # Официальный Content API (требует ключ продавца)
        endpoints.append(
            {
                "url": "https://content-api.wildberries.ru/content/v2/get/subjects",
                "headers": {"Authorization": api_key},
                "method": "GET",
            }
        )

    # Публичные endpoints (могут работать без ключа)
    endpoints.extend(
        [
            {
                "url": "https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm=1",
                "headers": {"User-Agent": "Mozilla/5.0"},
                "method": "GET",
            },
            {
                "url": "https://www.wildberries.ru/webapi/content/subjects",
                "headers": {"User-Agent": "Mozilla/5.0"},
                "method": "GET",
            },
        ]
    )

    for ep in endpoints:
        try:
            print(f"   Пробуем: {ep['url']}")
            response = requests.request(ep["method"], ep["url"], headers=ep["headers"], timeout=10)

            if response.status_code == 200:
                data = response.json()
                subjects = {}

                # Обрабатываем формат ответа Content API
                if isinstance(data, list):
                    for item in data:
                        subject_id = str(item.get("subjectID", item.get("id", "")))
                        if subject_id:
                            subjects[subject_id] = {
                                "id": int(subject_id),
                                "name": item.get("subjectName", item.get("name", "Без названия")),
                                "parent_id": item.get("parentSubjectID"),
                            }
                elif isinstance(data, dict):
                    # Формат {"subjects": [...]}
                    items = data.get("subjects", data.get("data", []))
                    if isinstance(items, list):
                        for item in items:
                            subject_id = str(item.get("subjectID", item.get("id", "")))
                            if subject_id:
                                subjects[subject_id] = {
                                    "id": int(subject_id),
                                    "name": item.get(
                                        "subjectName", item.get("name", "Без названия")
                                    ),
                                    "parent_id": item.get("parentSubjectID"),
                                }

                if subjects:
                    print(f"   ✅ Получено {len(subjects)} категорий WB")
                    return subjects

        except Exception as e:
            print(f"   ⚠️  Не удалось ({e.__class__.__name__})")
            continue

    # Fallback: локальный справочник
    print("   ⚠️  API недоступен, используем локальный справочник")
    return _load_local_wb_subjects()


# ============================================
# OZON (требует Client-Id и Api-Key)
# ============================================
def fetch_ozon_categories(client_id: str, api_key: str) -> dict:
    """
    Получает дерево категорий Ozon
    Docs: https://docs.ozon.ru/api/seller/#operation/DescriptionCategoryAPI_DescriptionCategoryTree
    """
    print("📦 Получаем категории Ozon...")

    if not client_id or not api_key:
        print("   ⚠️  Ключи Ozon не указаны — используем тестовые данные")
        return _get_mock_ozon_categories()

    url = "https://api-seller.ozon.ru/v1/description-category/tree"
    headers = {"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json"}
    payload = {"language": "DEFAULT"}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Парсим дерево категорий в плоский список
        categories = {}

        def flatten_tree(items, parent_id=None):
            for item in items:
                cat_id = str(item.get("category_id", ""))
                categories[cat_id] = {
                    "id": int(cat_id),
                    "name": item.get("title", item.get("name", "Без названия")),
                    "parent_id": parent_id,
                }
                # Рекурсивно обрабатываем вложенные категории
                if item.get("children"):
                    flatten_tree(item["children"], cat_id)

        if data.get("result"):
            flatten_tree(data["result"])

        print(f"   ✅ Получено {len(categories)} категорий Ozon")
        return categories

    except Exception as e:
        print(f"   ❌ Ошибка получения Ozon категорий: {e}")
        return _get_mock_ozon_categories()


def _get_mock_ozon_categories() -> dict:
    """Тестовые категории Ozon (если нет реальных ключей)"""
    return {
        "1": {"id": 1, "name": "Дом и сад", "parent_id": None},
        "101": {"id": 101, "name": "Уборка", "parent_id": 1},
        "10101": {"id": 10101, "name": "Швабры", "parent_id": 101},
        "10102": {"id": 10102, "name": "Вёдра", "parent_id": 101},
        "2": {"id": 2, "name": "Посуда", "parent_id": None},
        "201": {"id": 201, "name": "Миски и салатники", "parent_id": 2},
        "3": {"id": 3, "name": "Электроника", "parent_id": None},
        "301": {"id": 301, "name": "Аудиотехника", "parent_id": 3},
        "30101": {"id": 30101, "name": "Наушники", "parent_id": 301},
        "4": {"id": 4, "name": "Одежда", "parent_id": None},
        "401": {"id": 401, "name": "Мужская одежда", "parent_id": 4},
        "40101": {"id": 40101, "name": "Футболки", "parent_id": 401},
        "5": {"id": 5, "name": "Книги", "parent_id": None},
        "501": {"id": 501, "name": "Программирование", "parent_id": 5},
    }


# ============================================
# АВТОМАТИЧЕСКИЙ МАППИНГ
# ============================================
def build_mapping(ozon_cats: dict, wb_subjects: dict) -> dict:
    """
    Строит маппинг Ozon → Wildberries на основе названий
    Использует эвристику по ключевым словам
    """
    print("🔗 Строим маппинг категорий...")

    mapping = {}

    # Ключевые слова для соответствия
    keyword_rules = [
        (["уборка", "швабра", "ведро", "швабр", "поломоеч"], "1"),
        (["посуда", "миск", "салатник", "тарелк", "кружк", "стакан"], "2"),
        (["электрон", "аудио", "видео", "наушник", "колонк", "телефон"], "3"),
        (["одежд", "футболк", "рубашк", "брюк", "плать", "джинс"], "4"),
        (["книг", "журнал", "блокнот", "канцеляр"], "5"),
        (["игрушк", "детск", "малыш", "кукл", "машин"], "6"),
        (["красот", "здоров", "косметик", "уход"], "7"),
        (["спорт", "фитнес", "тренажёр", "велосипед"], "8"),
        (["продукт", "еда", "напитк", "чай", "кофе"], "9"),
        (["животн", "зоо", "корм", "игрушк для животн"], "10"),
    ]

    for ozon_id, ozon_cat in ozon_cats.items():
        ozon_name = ozon_cat.get("name", "").lower()

        # Ищем подходящую категорию WB по ключевым словам
        for keywords, wb_id in keyword_rules:
            if any(kw in ozon_name for kw in keywords):
                mapping[ozon_id] = wb_id
                break

        # Если не нашли — маппим на родительскую категорию или дефолт
        if ozon_id not in mapping:
            parent_id = ozon_cat.get("parent_id")
            if parent_id and str(parent_id) in mapping:
                mapping[ozon_id] = mapping[str(parent_id)]
            else:
                mapping[ozon_id] = "1"  # Дефолт: "Товары для дома"

    print(f"   ✅ Создано {len(mapping)} правил маппинга")
    return mapping


# ============================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================
def main():
    print("=" * 50)
    print("🚀 Загрузка категорий маркетплейсов")
    print("=" * 50)

    # 1. Получаем WB категории
    # Если есть ключ — используем реальный API
    # Если нет — автоматически используется локальный справочник
    WB_API_KEY = ""  # Вставьте сюда ваш токен, если есть

    wb_subjects = fetch_wildberries_subjects(api_key=WB_API_KEY)

    # 2. Получаем Ozon категории
    OZON_CLIENT_ID = ""
    OZON_API_KEY = ""

    ozon_cats = fetch_ozon_categories(client_id=OZON_CLIENT_ID, api_key=OZON_API_KEY)

    # 3. Строим маппинг
    mapping = build_mapping(ozon_cats, wb_subjects)

    # 4. Сохраняем
    result = {
        "last_updated": "2026-09-08",
        "ozon_categories": ozon_cats,
        "wildberries_subjects": wb_subjects,
        "mapping": {"ozon_to_wildberries": mapping},
        "stats": {
            "ozon_total": len(ozon_cats),
            "wb_total": len(wb_subjects),
            "mapping_rules": len(mapping),
        },
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Сохранено в: {OUTPUT_FILE}")
    print(f"📊 Статистика: {result['stats']}")


if __name__ == "__main__":
    main()
