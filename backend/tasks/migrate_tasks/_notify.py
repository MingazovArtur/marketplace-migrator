"""Письмо «пакетная миграция завершена» (v5).

Отправляется, если у пользователя включены уведомления (notify_batch_done)
и подтверждён email. Ошибка отправки не роняет задачу.
"""

import logging

from core.platforms import PLATFORM_CONFIG
from database.models import User
from database.session import SessionLocal

logger = logging.getLogger(__name__)


def _notify_batch_done(
    user_id: int,
    target_platform: str,
    total: int,
    success_count: int,
    error_count: int,
    duration_ms: int,
    errors: list,
) -> None:
    """
    ✅ v5: письмо «пакетная миграция завершена» — если у пользователя включены
    уведомления и подтверждён email. Ошибка отправки не роняет задачу.
    """
    try:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if (
                not user
                or not user.email
                or not user.email_verified_at
                or user.notify_batch_done is False
            ):
                return
            username = user.username
            to_email = user.email

        from services.email_service import send_batch_migration_email_sync

        send_batch_migration_email_sync(
            to_email=to_email,
            username=username,
            platform_name=PLATFORM_CONFIG.get(target_platform, {}).get(
                "name", target_platform
            ),
            total=total,
            success=success_count,
            errors=error_count,
            duration_ms=duration_ms,
            error_sample=errors[:5],
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"📧 Уведомление о пакете не отправлено (user={user_id}): {e}")
