"""
Реестр загрузок спеков площадок для админ-мониторинга.

Проблема: refresh_specs_task крутится в воркере с --pool=solo — параллельные
загрузки стоят в очереди Redis, и снаружи (кроме запустившего пользователя
с его task_id) их не видно. Этот пакет ведёт в Redis реестр всех загрузок:

  specs:task:{task_id}   JSON-инфо задачи (TTL 24 ч — после падения воркера
                         «зависшая» запись исчезает сама, реестр не гниёт)
  specs:tasks:active     SET id задач в очереди / в работе
  specs:tasks:history    LIST последних завершённых (обрезается до 50, TTL 7 дней)

Пауза/возобновление (админ, кооперативная остановка):
  specs:pause:{task_id}  флаг «админ просил паузу» — задача сама проверяет его
  specs:resumed:{old}    id новой задачи, которой продолжили старую (TTL 7 дней)

Р9 (разбиение монолита services/specs_monitor.py, 419 строк, на пакет — по
прецеденту category_service/ и routers/categories/ из docs/engineering.md):

  - _keys.py      — ключи Redis, TTL, сериализация записей (RESUMABLE_STATUSES)
  - _lifecycle.py — register / set_running / finish / get_info / sync_done_keys /
                    reconcile_on_startup (жизненный цикл записи задачи)
  - _pause.py     — request_pause / pause_requested / clear_pause /
                    mark_resumed / get_resumed (пауза и защита от повторного resume)
  - _queries.py   — list_active / list_history / is_stale (чтение для UI)

Публичный API сохранён без изменений: `from services import specs_monitor`
и атрибутный доступ (импортёры routers/categories/, tasks/catalog_tasks.py
не менялись).

Важно для тестов: redis_client импортирован отдельно в _lifecycle/_pause/
_queries — клиент подменяется в этих модулях (helper _set_redis в
tests/test_specs_monitor.py), а не на пакете.
"""

from services.specs_monitor._keys import RESUMABLE_STATUSES
from services.specs_monitor._lifecycle import (
    finish,
    get_info,
    reconcile_on_startup,
    register,
    set_running,
    sync_done_keys,
)
from services.specs_monitor._pause import (
    clear_pause,
    get_resumed,
    mark_resumed,
    pause_requested,
    request_pause,
)
from services.specs_monitor._queries import is_stale, list_active, list_history

__all__ = [
    "RESUMABLE_STATUSES",
    "register",
    "set_running",
    "finish",
    "get_info",
    "sync_done_keys",
    "reconcile_on_startup",
    "request_pause",
    "pause_requested",
    "clear_pause",
    "mark_resumed",
    "get_resumed",
    "list_active",
    "list_history",
    "is_stale",
]
