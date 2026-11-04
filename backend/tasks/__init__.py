"""
Celery задачи для фоновой миграции товаров, загрузки спеков площадок и тяжёлого XLSX-экспорта.

E-5 (неделя 4): монолит tasks.py (1300+ строк) разбит на пакет модулей
по доменам. Публичный API импортов сохранён 1:1 — `from tasks import X`
работает как раньше (routers/celery_app не менялись). Имена Celery-задач
заданы явно (name="tasks.*") и не зависят от пути модуля.

Модули:
  - recovery      — восстановление зависших 'processing' (B-3)
  - matching      — кэш спеков и подбор целевой категории (P-3)
  - progress      — чтение прогресса задачи (get_progress)
  - migrate_tasks — одиночная и пакетная миграция
  - media_tasks   — скачивание фото товаров
  - catalog_tasks — фоновая загрузка спеков площадок
  - export_tasks  — тяжёлый XLSX-экспорт (очередь xlsx_export)
"""

from tasks.catalog_tasks import refresh_specs_task
from tasks.export_tasks import generate_xlsx_export_task
from tasks.media_tasks import download_photos_task
from tasks.migrate_tasks import migrate_batch_task, migrate_product_task
from tasks.progress import get_progress
from tasks.recovery import recover_stuck_processing

__all__ = [
    "recover_stuck_processing",
    "get_progress",
    "migrate_product_task",
    "migrate_batch_task",
    "download_photos_task",
    "refresh_specs_task",
    "generate_xlsx_export_task",
]
