"""
Rate limiting на уровне приложения.
- Глобальные лимиты по IP
- Строгие лимиты для auth/import/migrate
- Авто-блокировка нарушителей (ban list в Redis)
- X-RateLimit заголовки в ответах
"""

import ipaddress
import logging

import redis
from fastapi import HTTPException, Request, status
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from core.config import settings

logger = logging.getLogger(__name__)

# Redis для хранения счётчиков и банов
_redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

# R-35 (В-7 ревью): атомарный INCR + EXPIRE. Раньше это были два отдельных
# вызова: процесс, умерший между ними, оставлял счётчик violations:* без TTL
# навсегда — счётчик больше не сбрасывался, и после трёх «вечных» нарушений
# идентификатор получал ложный пермабан. Lua-скрипт выполняется атомарно
# (одна команда Redis — заодно минус один RTT, В-6) и ставит TTL только
# при первом инкременте (c == 1), не перезаписывая TTL «зрелых» счётчиков.
_INCR_WITH_TTL = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return c
"""


def _incr_with_ttl(key: str, ttl_seconds: int) -> int:
    """INCR + EXPIRE атомарно (Lua); TTL ставится только при c == 1."""
    return int(_redis_client.eval(_INCR_WITH_TTL, 1, key, ttl_seconds))


# R-35 (К-3/В-9 ревью): отзыв JWT по jti. logout кладёт id токена в Redis
# на остаток его жизни, get_current_user отклоняет отозванные токены.
# Токены без jti (выданные до R-35) не отзываем — они просто доживают до exp.
# TTL обязателен: блэклист не должен переживать сам токен.
JWT_BLACKLIST_PREFIX = "jwt_blacklist:"


def revoke_token(jti: str, ttl_seconds: int) -> None:
    """Отозвать токен по jti на остаток времени его жизни."""
    if jti and ttl_seconds > 0:
        _redis_client.setex(f"{JWT_BLACKLIST_PREFIX}{jti}", int(ttl_seconds), "revoked")


def is_token_revoked(jti: str | None) -> bool:
    """Отозван ли токен (для токенов без jti — всегда False, без похода в Redis)."""
    if not jti:
        return False
    return bool(_redis_client.exists(f"{JWT_BLACKLIST_PREFIX}{jti}"))


def _valid_ip(value: str) -> str | None:
    """Возвращает значение, если это корректный IP, иначе None (анти-мусор в ключах Redis)."""
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        return None


def get_client_ip(request: Request) -> str:
    """
    Реальный IP клиента за nginx.

    Было 🔴 K-3 из код-ревью: брался ПЕРВЫЙ элемент X-Forwarded-For —
    его полностью контролирует клиент (`X-Forwarded-For: 1.2.3.4`), что
    позволяло обходить rate-limit и баны.

    Теперь:
      1) X-Real-IP — его проставляет наш nginx (`proxy_set_header X-Real-IP
         $remote_addr`), значение от клиента перезаписывается — доверяем;
      2) X-Forwarded-For — берём ПОСЛЕДНИЙ (правый) элемент: именно его
         добавил наш nginx ($proxy_add_x_forwarded_for), левую часть
         (поддельные адреса) клиент мог вписать сам;
      3) request.client.host — прямое соединение (dev без прокси).

    Остаётся важным: порт бэкенда (8000) не должен быть доступен из
    интернета напрямую, минуя nginx, — иначе заголовки можно подделать.

    R-35 (К-2), про dev-окружение: дев-фронт (docker-compose) сам слушает
    0.0.0.0:5173 и проксирует /api на backend (vite.config.js). Для API
    все такие запросы приходят «с IP контейнера фронта»: LAN-клиенты не
    различаются, баны по IP в dev-сети фактически не работают. Это
    осознанный dev-компромисс (dev-сеть считается доверенной; залог —
    комментарий в vite.config.js). В проде фронт — статика за nginx, он
    же проксирует /api и проставляет X-Real-IP, инвариант не нарушается.
    """
    xri = request.headers.get("x-real-ip")
    if xri:
        ip = _valid_ip(xri.strip())
        if ip:
            return ip

    xff = request.headers.get("x-forwarded-for")
    if xff:
        # Правый элемент — добавлен нашим nginx (клиентские подделки всегда левее)
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            ip = _valid_ip(parts[-1])
            if ip:
                return ip

    return request.client.host if request.client else "127.0.0.1"


def get_user_identifier(request: Request) -> str:
    """
    Идентификатор для лимитов:
    - Если пользователь авторизован → user_id (сильнее, чем IP)
    - Иначе → IP
    """
    # Пытаемся получить user_id из JWT (если есть). Payload берём из
    # request.state, если ban_check middleware уже декодировал этот токен
    # (R-35), иначе декодируем сами и кэшируем для get_current_user.
    try:
        from core.auth import get_jwt_payload_cached

        payload = get_jwt_payload_cached(request)
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

    Счётчики инкрементируются атомарным INCR+EXPIRE (Lua, R-35 В-6/В-7) —
    ключ не может остаться без TTL, RTT сокращены с четырёх до двух.
    """
    key = f"violations:{identifier}"
    count = _incr_with_ttl(key, 3600)  # окно 1 час

    # 3 нарушения за час → бан на 15 минут
    if count >= 3 and not is_banned(identifier):
        ban_identifier(identifier, 900, f"{count} нарушений за час")
        return count

    # 10 нарушений за день → бан на 24 часа (отдельный счётчик)
    day_key = f"violations_day:{identifier}"
    day_count = _incr_with_ttl(day_key, 86400)  # окно 24 часа
    if day_count >= 10 and not is_banned(identifier):
        ban_identifier(identifier, 86400, f"{day_count} нарушений за день")

    return count


# Глобальный лимитер
limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=settings.REDIS_URL,
    strategy="fixed-window",
    # R29: общий зонт на все эндпоинты без собственного лимита. Раньше комментарий
    # в routers/auth.py обещал «глобальный 100/min из middleware», но default_limits
    # не был задан — эндпоинты без @limiter.limit не имели ограничений вовсе.
    default_limits=["200/minute"],
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
