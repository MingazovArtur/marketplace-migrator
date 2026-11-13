"""Сверка реестра спеков при старте спек-воркера (--pool=solo).

Вынесено без изменений из монолита tasks/catalog_tasks.py (Р22).
Обработчик подключается к сигналу worker_ready при импорте модуля —
пакет импортирует его в __init__ (side-effect), как раньше при импорте
монолита.
"""

import logging
import os

from celery.signals import worker_ready
from services import specs_monitor
from tasks.progress import get_progress

logger = logging.getLogger(__name__)


# ==================== Сверка реестра при старте спек-воркера ====================


@worker_ready.connect
def _reconcile_specs_registry_on_worker_start(sender=None, **kwargs):
    """
    Спек-воркер только что стартовал (--pool=solo) — значит, ни одна загрузка
    спеков сейчас не выполняется. Все записи реестра в state=running —
    «трупы» задач, убитых вместе с прошлым воркером (docker compose down,
    crash, OOM): помечаем их «прервана», чтобы админ мог продолжить
    с последнего сохранённого прогресса.

    Работает только в контейнере спек-воркера (env SPECS_WORKER=1): обычный
    и xlsx-воркеры при старте ничего не помечают (иначе перезапуск соседа
    ложно «прерывал» бы живую загрузку).
    """
    if os.getenv("SPECS_WORKER") != "1":
        return
    try:
        closed = specs_monitor.reconcile_on_startup(live=get_progress)
        if closed:
            logger.info(
                f"⏸ Старт спек-воркера: {closed} записей мониторинга помечено «прервана» "
                "(задачи убиты перезапуском воркера)"
            )
    except Exception as e:
        logger.warning(f"Сверка реестра спеков при старте воркера не выполнена: {e}")
