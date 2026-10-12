"""
Rate limiting на уровне приложения.
- Глобальные лимиты по IP
- Строгие лимиты для auth/import/migrate
- Авто-блокировка нарушителей (ban list в Redis)
- X-RateLimit заголовки в ответах
"""

import logging

import redis
from fastapi import HTTPException, Request, status
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from core.config import settings

logger = logging.getLogger(__name__)

# Redis для хранения счётчиков и банов
_redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_client_ip(request: Request) -> str:
    """Реальный IP за nginx (X-Forwarded-For)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else "127.0.0.1"


def get_user_identifier(request: Request) -> str:
    """
    Идентификатор для лимитов:
    - Если пользователь авторизован → user_id (сильнее, чем IP)
    - Иначе → IP
    """
    # Пытаемся получить user_id из JWT (если есть)
    try:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            from core.auth import decode_token

            payload = decode_token(token)
            if payload and "sub" in payload:
                return f"user:{payload['sub']}"
    except Exception:
        pass
    return f"ip:{get_client_ip(request)}"


def is_banned(identifier: str) -> bool:
    """Проверка, забанен ли пользователь/IP."""
    return _redis_client.exists(f"ban:{identifier}")


def ban_identifier(identifier: str, duration_seconds: int, reason: str):
    """Забанить идентификатор на указанное время."""
    _redis_client.setex(f"ban:{identifier}", duration_seconds, reason)
    logger.warning(f"🚫 Бан: {identifier} на {duration_seconds}с — {reason}")


def record_violation(identifier: str) -> int:
    """
    Записать нарушение лимита, вернуть количество нарушений за последний час.
    Автоматически банит при превышении порога.
    """
    key = f"violations:{identifier}"
    count = _redis_client.incr(key)
    _redis_client.expire(key, 3600)  # окно 1 час

    # 3 нарушения за час → бан на 15 минут
    if count >= 3 and not is_banned(identifier):
        ban_identifier(identifier, 900, f"{count} нарушений за час")
        return count

    # 10 нарушений за день → бан на 24 часа (отдельный счётчик)
    day_key = f"violations_day:{identifier}"
    day_count = _redis_client.incr(day_key)
    _redis_client.expire(day_key, 86400)  # окно 24 часа
    if day_count >= 10 and not is_banned(identifier):
        ban_identifier(identifier, 86400, f"{day_count} нарушений за день")

    return count


# Глобальный лимитер
limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=settings.REDIS_URL,
    strategy="fixed-window",
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Обработчик превышения лимита."""
    identifier = get_user_identifier(request)
    record_violation(identifier)

    logger.warning(
        f"⚠️ Rate limit exceeded: {request.method} {request.url.path} | {identifier} | "
        f"limit={exc.detail}"
    )

    if is_banned(identifier):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ временно ограничен из-за подозрительной активности",
        )

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Слишком много запросов: {exc.detail}. Повторите позже.",
    )
