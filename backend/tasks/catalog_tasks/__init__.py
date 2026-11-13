"""
Фоновая загрузка спеков площадок (Ozon, Яндекс Маркет, Wildberries).

Р22 (разбиение монолита tasks/catalog_tasks.py, 297 строк, на пакет — по
прецеденту tasks/migrate_tasks/ (Р15)):

  - _refresh.py   — refresh_specs_task: единая фоновая загрузка спеков
                    категорий площадки через её API с прогресс-баром,
                    паузами (resume по done_keys), расшифровкой API-ключа
                    (В-4), сбросом кэшей (P-3) и статистикой
  - _reconcile.py — _reconcile_specs_registry_on_worker_start: сверка
                    реестра мониторинга при старте спек-воркера
                    (@worker_ready.connect, только SPECS_WORKER=1)

Имя Celery-задачи явное (name="tasks.refresh_specs_task") и НЕ зависит
от пути модуля (правило engineering.md): регистрация декоратором
@celery_app.task при импорте _refresh и маршрутизация очередей
(celery_app.py: include=["tasks"] → tasks/__init__.py → этот пакет,
task_routes → очередь specs) стабильны.

Обработчик worker_ready подключается при импорте _reconcile ниже —
side-effect импорта пакета, ровно как раньше при импорте монолита.

Публичный API сохранён без изменений: `from tasks.catalog_tasks import
refresh_specs_task` (единственный импортёр — tasks/__init__.py — не
менялся); `from tasks import refresh_specs_task` работает как раньше.
"""

from tasks.catalog_tasks._reconcile import _reconcile_specs_registry_on_worker_start
from tasks.catalog_tasks._refresh import refresh_specs_task

__all__ = [
    "refresh_specs_task",
    "_reconcile_specs_registry_on_worker_start",
]
