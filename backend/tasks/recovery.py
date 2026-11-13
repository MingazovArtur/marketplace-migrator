"""
B-3 (неделя 2): восстановление зависших статусов 'processing'.

Проблема из код-ревью: если воркер умирает/рестартует во время миграции,
товары навсегда остаются в статусе 'processing' («вечный спиннер» у юзера).

Решение: при старте воркера очереди default (только он ставит 'processing' —
это задачи миграций) зависшие товары возвращаются в 'error' с понятным
сообщением, юзер может повторить миграцию. Beat в проде не используется,
поэтому worker_ready — надёжная точка восстановления после любого рестарта.
Guard: xlsx-воркер (очередь xlsx_export) статусы товаров не пишет —
рестарт его контейнера не должен сбрасывать чужие in-flight миграции.
"""

import logging

from celery.signals import worker_ready

from core.time import utcnow

logger = logging.getLogger(__name__)


def recover_stuck_processing(session_factory=None) -> int:
    """
    Возвращает ВСЕ товары в статусе 'processing' в 'error' с понятным сообщением.
    Идемпотентно, безопасно при повторном вызове. Возвращает число восстановленных.
    Вызывается при старте default-воркера (worker_ready) — в этот момент
    выполняемых задач миграции нет, значит все 'processing' — сироты.
    """
    from database.models import Product
    from database.session import SessionLocal

    factory = session_factory or SessionLocal
    with factory() as db:
        recovered = (
            db.query(Product)
            .filter(Product.status == "processing")
            .update(
                {
                    "status": "error",
                    "error_message": (
                        "Миграция прервана (перезапуск сервиса). "
                        "Повторите миграцию — данные не потеряны."
                    ),
                    "updated_at": utcnow(),
                },
                synchronize_session=False,
            )
        )
        db.commit()
    return recovered or 0


@worker_ready.connect
def _recover_stuck_processing_on_boot(sender=None, **kwargs):
    """Хук старта воркера: сброс зависших 'processing' (B-3)."""
    hostname = str(getattr(sender, "hostname", "") or "")
    if "xlsx" in hostname.lower():
        logger.info("🔄 B-3 recovery пропущен: это xlsx-воркер (не ставит 'processing')")
        return
    try:
        recovered = recover_stuck_processing()
        if recovered:
            logger.warning(
                f"🔄 B-3 recovery: возвращено из 'processing' в 'error' товаров: {recovered}"
            )
        else:
            logger.info("🔄 B-3 recovery: зависших 'processing' товаров нет")
    except Exception as e:
        # Recovery — не причина падать на старте: логируем и продолжаем
        logger.error(f"❌ B-3 recovery не выполнен: {e}")
