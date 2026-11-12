"""
Роутер категорий: справочники категорий площадок, спецификации категорий,
админ-мониторинг загрузок спеков, маппинг категорий.

Р7 (разбиение монолита routers/categories.py, 687 строк, на пакет — по
прецеденту routers/export/ из docs/engineering.md):

  - _support.py     — доступ админа, payloads, фильтр инфо задач
  - specs_refresh.py— обновление спеков через API площадок (Celery) + прогресс + key-source
  - specs_admin.py  — админ-мониторинг загрузок спеков (список/пауза/возобновление)
  - specs.py        — чтение/удаление спеков (names, список, одиночные)
  - catalog.py      — справочники категорий: список/дерево/обновление по ключу
  - mappings.py     — маппинг категорий: список/сохранение/удаление

Публичный API сохранён: `from routers import categories; categories.router`
(main.py не менялся).

ВАЖНО — порядок include_router ниже:
catch-all /specs/{platform}/{category_id:path} (модуль specs) должен
регистрироваться ПОСЛЕ фиксированных /specs/{platform}/refresh/...,
/key-source (specs_refresh) и /specs/{platform}/names (specs) — иначе
эти пути ловились бы как category_id. Внутри specs.py /names также
объявлен до catch-all.
"""

from fastapi import APIRouter

from routers.categories.catalog import router as catalog_router
from routers.categories.mappings import router as mappings_router
from routers.categories.specs import router as specs_router
from routers.categories.specs_admin import router as specs_admin_router
from routers.categories.specs_refresh import router as specs_refresh_router

router = APIRouter(prefix="/api", tags=["Categories"])
router.include_router(specs_refresh_router)
router.include_router(specs_admin_router)
router.include_router(specs_router)
router.include_router(catalog_router)
router.include_router(mappings_router)
