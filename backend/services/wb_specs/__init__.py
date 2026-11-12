"""
Загрузчик спецификаций Wildberries через Content API v2[cite: 12].

Эндпоинты[cite: 12]:
- GET  /content/v2/object/parent/all            → все предметы (subjects)[cite: 12]
- POST /content/v2/object/characteristics/list  → характеристики предмета[cite: 12]
- GET  /content/v2/directory/{directoryID}      → значения словаря[cite: 12]

Авторизация: сырой токен в заголовке Authorization (без схемы)[cite: 12].
Документация: https://dev.wildberries.ru/docs/openapi/item-management[cite: 12]

Р17 (разбиение монолита services/wb_specs.py, 313 строк, на пакет — по
прецеденту ozon_specs/ из Р8 и yandex_specs/ из Р16, docs/engineering.md):

  - _http.py            — WB_API_BASE, сырой токен в Authorization
                          (без Bearer/OAuth)
  - _subjects.py        — все предметы WB (GET /content/v2/object/parent/all)
  - _characteristics.py — характеристики предмета + значения словарей,
                          эвристики типов/групп, правила валидации и
                          спецтребования
  - _storage.py         — upsert PlatformCategorySpec по
                          (platform, category_id)
  - _refresh.py         — оркестратор refresh_wildberries_specs: пауза
                          перед каждым предметом, задержка между запросами
                          (WB_REQUEST_DELAY), прогресс (PROGRESS_EVERY)

Публичный API сохранён без изменений: `from services.wb_specs import
refresh_wildberries_specs` (импортёр tasks/catalog_tasks.py не менялся);
константы доступны на пакете, как и в монолите.
"""

from services.wb_specs._http import WB_API_BASE, _wb_headers
from services.wb_specs._refresh import (
    PROGRESS_EVERY,
    WB_REQUEST_DELAY,
    refresh_wildberries_specs,
)
from services.wb_specs._subjects import fetch_wb_subjects
from services.wb_specs._characteristics import (
    fetch_wb_characteristics,
    fetch_wb_directory,
)

__all__ = [
    # Публичный API
    "refresh_wildberries_specs",
    "fetch_wb_subjects",
    "fetch_wb_characteristics",
    "fetch_wb_directory",
    # Константы (для совместимости с монолитом)
    "WB_API_BASE",
    "WB_REQUEST_DELAY",
    "PROGRESS_EVERY",
]
