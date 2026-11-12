"""
Роутер экспорта: выгрузка файлов для ЛК площадок, предпросмотр, валидация, шаблоны.

Р1 (разбиение монолита routers/export.py, 985 строк, на пакет — по прецеденту
tasks/, repository/, xlsx_generator/ из docs/engineering.md):

  - _support.py      — IDOR-реестр задач, content-disposition, парсинг id, константы
  - _queries.py      — асинхронные выборки товаров/спек, product_to_dict, mark_exported
  - _xlsx_dispatch.py— диспетчер «Celery xlsx_export или поток»
  - templates.py     — эталонные шаблоны площадок (6 эндпоинтов)
  - preview.py       — предпросмотр + валидация по спекам
  - files.py         — шаблон выгрузки, файл для ЛК, отчёт по миграции
  - xlsx.py          — XLSX v2 + async-постановка + статусы/скачивание задач

Публичный API сохранён: `from routers import export; export.router`
(main.py не менялся).

✅ v4 (инкрементальный экспорт), v8 (AsyncSession + очередь xlsx_export),
IDOR-защита В-2 и админ-гейты эталонов — поведение без изменений.
"""

from fastapi import APIRouter

from routers.export.files import router as files_router
from routers.export.preview import router as preview_router
from routers.export.templates import router as templates_router
from routers.export.xlsx import router as xlsx_router

router = APIRouter(prefix="/api", tags=["Export"])
router.include_router(templates_router)
router.include_router(files_router)
router.include_router(preview_router)
router.include_router(xlsx_router)
