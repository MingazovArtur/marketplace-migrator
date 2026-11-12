"""
Роутер импорта товаров (API-ключ, YML, Excel/CSV).

Р13 (разбиение монолита routers/import_router.py, 612 строк, на пакет —
по прецеденту routers/export/ (Р1) и routers/products/ (Р10)):

  - _support.py     — ImportRequest, MAX_IMPORT_FILE_SIZE,
                      синхронная запись _persist_imported_products
                      (repo.bulk_import), метка источника, разбор ключа
                      Яндекс Маркета
  - _preview.py     — POST /import/preview: первые строки + ошибки
                      парсинга (без записи в БД)
  - _key_import.py  — POST /import: мок-ключ, YML-фид по ссылке,
                      реальный API Яндекс Маркета
  - _file_import.py — POST /import/file: XLSX/CSV, режимы create/upsert

Режимы импорта файла:
  - create — только новые карточки
  - upsert — обновление совпадений по external_id / sku

Все операции логируются в file_operation_logs (журнал) и
import_export_stats (статистика с замером времени).

Rate-limits (на идентификатор: user_id или IP):
  - /import/preview : 30/min
  - /import (key/yml): 10/min, 100/day
  - /import/file    : 10/min, 100/day

B-1 (неделя 2): CPU-тяжёлый парсинг (openpyxl) и цикл записи в БД
выносятся из async-роута в threadpool (asyncio.to_thread) —
больше не блокируют event loop на весь импорт.

Публичный API сохранён: `from routers import import_router;
import_router.router` (main.py не менялся); ImportRequest,
MAX_IMPORT_FILE_SIZE, эндпоинты и точки патчинга (repo / op_log /
stats_repo — модули database.repository) остались на пакете теми же
объектами, что в подмодулях.

Все 3 маршрута фиксированные (параметрических нет) — порядок
include_router ниже на матчинг не влияет; порядок сохранён как в
монолите (preview, import, file). Логгеры подмодулей — иерархические
дети «routers.import_router» (routers.import_router._key_import и т.д.):
конфигурация логирования по имени «routers.import_router» продолжает
действовать на все подмодули.
"""

from fastapi import APIRouter

from routers.import_router._file_import import router as file_import_router
from routers.import_router._key_import import router as key_import_router
from routers.import_router._preview import router as preview_router

router = APIRouter(prefix="/api", tags=["Import"])
router.include_router(preview_router)
router.include_router(key_import_router)
router.include_router(file_import_router)

# Публичные имена монолита для импортёров и тестов (точки патчинга —
# модули database.repository: repo / op_log / stats_repo, те же объекты,
# что используют подмодули).
from database.repository import op_log, repo, stats_repo  # noqa: E402
from routers.import_router._file_import import import_from_file  # noqa: E402
from routers.import_router._key_import import import_products  # noqa: E402
from routers.import_router._preview import preview_import  # noqa: E402
from routers.import_router._support import (  # noqa: E402
    MAX_IMPORT_FILE_SIZE,
    ImportRequest,
)
