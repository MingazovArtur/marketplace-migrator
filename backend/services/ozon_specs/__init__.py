"""
Загрузчик спецификаций категорий Ozon через официальный Seller API.

v3 — оптимизация памяти: CONCURRENCY=5, DB_CHUNK=50, gc.collect() после
каждого чанка. Ожидаемое время загрузки: 20-40 минут (медленнее, но
стабильно на 2GB RAM).

Эндпоинты Ozon:
- POST /v1/description-category/tree             → дерево категорий (_tree)
- POST /v1/description-category/attribute        → атрибуты категории (_attributes)
- POST /v1/description-category/attribute/values → значения словаря (_attributes)

Р8 (разбиение монолита services/ozon_specs.py, 635 строк, на пакет — по
прецеденту category_service/ и template_filler/ из docs/engineering.md):

  - _http.py       — заголовки, разбор API-ключа, POST с retry и семафором
                     (OZON_API_BASE, CONCURRENCY, TIMEOUT, MAX_RETRIES)
  - _tree.py       — дерево категорий → плоский список листьев
  - _attributes.py — словари значений, маппинг типов, сборка спека и правил
                     валидации (MAX_VALUES_PER_ATTR, MAX_DICT_PAGES,
                     BASE_REQUIRED_FIELDS)
  - _storage.py    — пакетная запись в БД, upsert по (platform, category_id)
                     (DB_CHUNK)
  - _refresh.py    — оркестратор refresh_ozon_specs: чанки, пауза/продолжение
                     после паузы, прогресс (PROGRESS_EVERY)

Публичный API сохранён без изменений: `from services.ozon_specs import
refresh_ozon_specs` (импортёр tasks/catalog_tasks.py не менялся); константы
доступны на пакете, как и в монолите.
"""

from services.ozon_specs._attributes import (
    BASE_REQUIRED_FIELDS,
    MAX_DICT_PAGES,
    MAX_VALUES_PER_ATTR,
)
from services.ozon_specs._http import (
    CONCURRENCY,
    MAX_RETRIES,
    OZON_API_BASE,
    TIMEOUT,
)
from services.ozon_specs._refresh import PROGRESS_EVERY, refresh_ozon_specs
from services.ozon_specs._storage import DB_CHUNK
from services.ozon_specs._tree import fetch_ozon_category_tree

__all__ = [
    # Публичный API
    "refresh_ozon_specs",
    "fetch_ozon_category_tree",
    # Константы (для совместимости с монолитом)
    "OZON_API_BASE",
    "CONCURRENCY",
    "TIMEOUT",
    "MAX_RETRIES",
    "MAX_VALUES_PER_ATTR",
    "MAX_DICT_PAGES",
    "DB_CHUNK",
    "PROGRESS_EVERY",
    "BASE_REQUIRED_FIELDS",
]
