"""
Email-сервис: отправка писем с HTML-шаблонами.
- Подтверждение email (verify)
- Сброс пароля (reset password)
- Приветственное письмо (welcome)

Токены:
  - verify: JWT с claim type=verify, TTL 24h
  - reset: случайный token_urlsafe(32), в БД только SHA-256 hash, TTL 1h
"""

import asyncio
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader

from core.auth import create_access_token
from core.config import settings
from database.models import PasswordResetToken, User
from database.session import SessionLocal

logger = logging.getLogger(__name__)

# Шаблоны писем: backend/services/email_templates/*.html
TEMPLATES_DIR = Path(__file__).parent / "email_templates"
_jinja = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


def _render(template_name: str, context: dict) -> str:
    """Рендер HTML-шаблона письма."""
    tpl = _jinja.get_template(template_name)
    return tpl.render(**context)


async def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Отправка письма через SMTP (async). Возвращает True при успехе."""
    if not settings.SMTP_HOST:
        logger.warning(f"📧 SMTP не настроен. Письмо НЕ отправлено: {to_email} | {subject}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_TLS,
            start_tls=not settings.SMTP_TLS,
        )
        logger.info(f"📧 ✅ Письмо отправлено: {to_email} | {subject}")
        return True
    except Exception as e:
        logger.error(f"📧 ❌ Ошибка отправки письма {to_email}: {e}")
        return False


# ============================================================
# Генерация токенов
# ============================================================


def generate_verify_token(user: User) -> str:
    """JWT-токен для подтверждения email (24h)."""
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "type": "verify",
    }
    return create_access_token(payload, expires_delta=timedelta(hours=24))


def generate_reset_token(user: User) -> tuple[str, str]:
    """
    Случайный токен сброса пароля (1h).
    Возвращает (raw_token, token_hash) — в БД сохраняем только hash.
    """
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()

    db = SessionLocal()
    try:
        # Отзываем все предыдущие токены этого пользователя
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({PasswordResetToken.used_at: datetime.now(UTC)})

        token_obj = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(token_obj)
        db.commit()
        return raw, token_hash
    finally:
        db.close()


def validate_reset_token(raw_token: str):
    """Валидация токена сброса. Возвращает User или None."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db = SessionLocal()
    try:
        token_obj = (
            db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > datetime.now(UTC),
            )
            .first()
        )
        if not token_obj:
            return None

        # Помечаем как использованный
        token_obj.used_at = datetime.now(UTC)
        db.commit()

        return db.query(User).filter(User.id == token_obj.user_id).first()
    finally:
        db.close()


# ============================================================
# Отправка конкретных типов писем
# ============================================================


async def send_verification_email(user: User) -> bool:
    """Письмо подтверждения email (ссылка с JWT-токеном)."""
    token = generate_verify_token(user)
    verify_url = f"{settings.PUBLIC_URL}/#/verify-email?token={token}"

    html = _render(
        "verify_email.html",
        {
            "username": user.username,
            "verify_url": verify_url,
            "service_name": settings.SMTP_FROM_NAME,
        },
    )
    return await _send_email(
        to_email=user.email,
        subject=f"Подтвердите email — {settings.SMTP_FROM_NAME}",
        html_body=html,
    )


async def send_password_reset_email(user: User) -> bool:
    """Письмо сброса пароля (ссылка с одноразовым токеном)."""
    # generate_reset_token пишет в БД синхронно (SessionLocal) —
    # выносим в threadpool, чтобы не блокировать event loop (B-1, неделя 2)
    raw_token, _ = await asyncio.to_thread(generate_reset_token, user)
    reset_url = f"{settings.PUBLIC_URL}/#/reset-password?token={raw_token}"

    html = _render(
        "reset_password.html",
        {
            "username": user.username,
            "reset_url": reset_url,
            "service_name": settings.SMTP_FROM_NAME,
            "expires_hours": 1,
        },
    )
    return await _send_email(
        to_email=user.email,
        subject=f"Сброс пароля — {settings.SMTP_FROM_NAME}",
        html_body=html,
    )


async def send_welcome_email(user: User) -> bool:
    """Приветственное письмо после верификации."""
    html = _render(
        "welcome.html",
        {
            "username": user.username,
            "login_url": f"{settings.PUBLIC_URL}/#/login",
            "service_name": settings.SMTP_FROM_NAME,
        },
    )
    return await _send_email(
        to_email=user.email,
        subject=f"Добро пожаловать в {settings.SMTP_FROM_NAME}!",
        html_body=html,
    )


# ============================================================
# ✅ v5: уведомление о завершении пакетной миграции
# ============================================================

async def send_batch_migration_email(
    to_email: str,
    username: str,
    platform_name: str,
    total: int,
    success: int,
    errors: int,
    duration_ms: int,
    error_sample: list[dict] | None = None,
) -> bool:
    """Письмо «пакетная миграция завершена» (итоги + первые ошибки)."""
    html = _render(
        "batch_done.html",
        {
            "username": username,
            "platform_name": platform_name,
            "total": total,
            "success": success,
            "errors": errors,
            "duration_sec": max(1, round((duration_ms or 0) / 1000)),
            "error_sample": (error_sample or [])[:5],
            "login_url": f"{settings.PUBLIC_URL}/#/login",
            "service_name": settings.SMTP_FROM_NAME,
        },
    )
    return await _send_email(
        to_email=to_email,
        subject=f"Пакетная миграция завершена: {success} из {total} — {settings.SMTP_FROM_NAME}",
        html_body=html,
    )


def send_batch_migration_email_sync(**context) -> bool:
    """
    Синхронная обёртка для Celery-задач (worker — синхронный процесс).
    Никогда не бросает исключений: письмо не должно ронять миграцию.
    """
    try:
        return asyncio.run(send_batch_migration_email(**context))
    except Exception as e:  # noqa: BLE001
        logger.error(f"📧 ❌ Не удалось отправить письмо о пакете: {e}")
        return False
