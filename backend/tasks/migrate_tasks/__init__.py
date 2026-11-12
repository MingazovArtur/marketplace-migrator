"""Одиночная и пакетная миграция товаров (Celery).

Р15 (разбиение монолита tasks/migrate_tasks.py, 529 строк, на пакет — по
прецедентам Р8–Р14 из docs/engineering.md):

  - _notify.py — письмо «пакетная миграция завершена» (v5): проверка
                 уведомлений пользователя (notify_batch_done + подтверждённый
                 email), ошибка отправки не роняет задачу
  - _single.py — migrate_product_task: одиночная миграция с проверкой
                 владельца, дефолтами, ценой по PRICE_RULES, журналом
  - _batch.py  — migrate_batch_task: пакетная миграция P-3 (bulk-статусы,
                 выборка чанками по 100, один update_batch на пакет, журнал
                 bulk insert чанками по 200, троттлинг прогресса)

Имена Celery-задач заданы явно (name="tasks.*") и НЕ зависят от пути
модуля (правило engineering.md): регистрация задач декоратором
@celery_app.task при импорте подмодулей и маршрутизация очередей
(celery_app.py: include=["tasks"] → tasks/__init__.py → этот пакет)
стабильны, воркеры и task_routes ничего не замечают.

Публичный API сохранён без изменений: `from tasks.migrate_tasks import
migrate_batch_task, migrate_product_task` (единственный импортёр —
tasks/__init__.py — не менялся); `from tasks import ...` работает как
раньше.
"""

from tasks.migrate_tasks._batch import migrate_batch_task
from tasks.migrate_tasks._single import migrate_product_task

__all__ = [
    "migrate_product_task",
    "migrate_batch_task",
]
