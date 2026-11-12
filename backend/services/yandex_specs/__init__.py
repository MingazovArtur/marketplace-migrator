"""
Загрузчик спецификаций категорий Яндекс Маркета через официальный Partner API.

Актуальные эндпоинты Partner API:
- POST /categories/tree                  → дерево всех категорий Маркета
- POST /category/{categoryId}/parameters → характеристики и словари значений листовой категории

Поддерживает современные API-ключи формата 'ACMA:...' (заголовок Api-Key)
и OAuth-токены (заголовок Authorization: OAuth).

Р16 (разбиение монолита services/yandex_specs.py, 443 строки, на пакет — по
прецеденту ozon_specs/ из Р8, docs/engineering.md):

  - _http.py       — заголовки (ACMA vs OAuth), POST с retry и семафором
                     (YANDEX_API_BASE, CONCURRENCY, TIMEOUT, MAX_RETRIES)
  - _tree.py       — дерево категорий → плоский список листьев
  - _parameters.py — маппинг типов/групп, характеристики категории, правила
                     валидации (MAX_VALUES_PER_ATTR, YM_BASE_REQUIRED_FIELDS)
  - _storage.py    — пакетная запись в БД, upsert по (platform, category_id)
                     (DB_CHUNK)
  - _refresh.py    — оркестратор refresh_yandex_specs: чанки, пауза/продолжение
                     после паузы, прогресс (PROGRESS_EVERY)

Публичный API сохранён без изменений: `from services.yandex_specs import
refresh_yandex_specs` (импортёр tasks/catalog_tasks.py не менялся); константы
доступны на пакете, как и в монолите.
"""

from services.yandex_specs._http import (
    CONCURRENCY,
    MAX_RETRIES,
    TIMEOUT,
    YANDEX_API_BASE,
)
from services.yandex_specs._parameters import (
    MAX_VALUES_PER_ATTR,
    YM_BASE_REQUIRED_FIELDS,
    fetch_yandex_category_parameters,
)
from services.yandex_specs._refresh import PROGRESS_EVERY, refresh_yandex_specs
from services.yandex_specs._storage import DB_CHUNK
from services.yandex_specs._tree import fetch_yandex_categories_tree

__all__ = [
    # Публичный API
    "refresh_yandex_specs",
    "fetch_yandex_categories_tree",
    "fetch_yandex_category_parameters",
    # Константы (для совместимости с монолитом)
    "YANDEX_API_BASE",
    "CONCURRENCY",
    "TIMEOUT",
    "MAX_RETRIES",
    "MAX_VALUES_PER_ATTR",
    "DB_CHUNK",
    "PROGRESS_EVERY",
    "YM_BASE_REQUIRED_FIELDS",
]
