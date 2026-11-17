"""
Главный файл приложения FastAPI

Порядок обработки запроса (от внешнего к внутреннему):
  Запрос → CORS → SlowAPI → GZip → ban_check → request-id → роутер
"""

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core.config import settings
from core.error_handler import register_exception_handlers
from core.logging_config import configure_logging, request_id_var
from core.platforms import PLATFORM_CONFIG, Platform
from core.rate_limit import (
    get_client_ip,
    is_banned,
    limiter,
    rate_limit_exceeded_handler,
)
from routers import (
    attributes,
    auth,
    categories,
    email_router,
    export,
    history,
    import_router,
    photos,
    products,
    profiles,
    stats,
    templates,
    tnved,
    variants,
)
from routers import (
    defaults as defaults_router,
)
from routers import (
    media as media_router,  # /media с авторизацией (замена StaticFiles)
)
from routers.health import router as health_router
from routers.migrate_router import router as migrate_router

# R-35 (В-12): формат с датой и request-id вместо голого basicConfig;
# при уже настроенном root (pytest/gunicorn) — no-op
configure_logging()
logger = logging.getLogger(__name__)


def _init_sentry() -> None:
    """R-35 (В-12): поля SENTRY_* в конфиге были, но sentry_sdk.init не
    вызывался нигде — интеграция существовала только на бумаге. Теперь:
    DSN задан → инициализируем (пакет опционален, ошибки импорта не фатальны).
    """
    dsn = getattr(settings, "SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN задан, но sentry-sdk не установлен — Sentry отключён")
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=getattr(settings, "SENTRY_ENVIRONMENT", "development"),
        release=getattr(settings, "SENTRY_RELEASE", "local"),
        send_default_pii=False,
        traces_sample_rate=0.0,
    )
    logger.info("Sentry инициализирован (env=%s)", settings.SENTRY_ENVIRONMENT)


_init_sentry()

# Было В-6 из код-ревью: /docs, /redoc и /openapi.json были доступны в проде
# и раскрывали полную карту API (в т.ч. внутренние эндпоинты).
# В production полностью отключаем; в dev оставляем.
_IS_PRODUCTION = getattr(settings, "ENVIRONMENT", "development") == "production"

app = FastAPI(
    title="Marketplace Migrator API",
    version="3.4",
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
)

# ============================================================
# 0. Централизованная обработка ошибок
# ============================================================
register_exception_handlers(app)


# ============================================================
# 1. Ban-check middleware
# ============================================================
@app.middleware("http")
async def ban_check_middleware(request: Request, call_next):
    """
    Проверяет бан IP и user_id перед обработкой запроса.
    Пропускает: healthcheck, статику, docs, OPTIONS (preflight).

    R-35 (В-6): проверки банов ушли в threadpool (asyncio.to_thread) —
    sync-redis-клиент больше не блокирует event loop каждого запроса;
    Redis недоступен → исключение (fail-closed), но без латентности для лупа.

    Асимметрия (В-9): здесь проверяем ТОЛЬКО баны по sub из токена —
    авторизация по роли всегда идёт через БД (get_current_admin_user),
    поэтому понижение роли применяется сразу и не зависит от содержимого
    токена.
    """
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path

    if path in ("/api/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)

    ip = get_client_ip(request)
    if await asyncio.to_thread(is_banned, f"ip:{ip}"):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Доступ временно ограничен из-за подозрительной активности"},
        )

    try:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            # R-35: payload кэшируется в request.state — rate-limiter и
            # get_current_user ниже по конвейеру не декодируют токен заново
            from core.auth import get_jwt_payload_cached

            payload = get_jwt_payload_cached(request, token)
            if payload and "sub" in payload:
                user_id = str(payload["sub"])
                if await asyncio.to_thread(is_banned, f"user:{user_id}"):
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Ваш аккаунт временно заблокирован"},
                    )
    except Exception as e:
        logger.debug(f"ban_check token parse failed: {e}")

    response = await call_next(request)
    return response


# ============================================================
# 1b. Request-ID middleware (Correlation-ID, R-35 В-12)
# ============================================================
# Регистрируется ПОСЛЕ ban_check → в рантайме стоит ВНЕШНЕГО него:
# request-id известен уже логам ban_check и доступен в ответах 403/500.
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Сквозной id запроса для склейки логов и сопоставления с ответом.

    Входящий X-Request-ID (короткая печатная ASCII-строка) принимается
    эхом — удобно прокидывать id из nginx; иначе генерируется новый.
    id попадает в заголовок ответа X-Request-ID и в каждую запись
    лога через RequestIdFilter (core/logging_config.py).
    """
    rid = (request.headers.get("x-request-id") or "").strip()
    if not (rid and rid.isascii() and rid.isprintable() and len(rid) <= 64):
        rid = uuid4().hex[:16]
    token = request_id_var.set(rid)
    request.state.request_id = rid
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    return response


# ============================================================
# 2. GZip — сжатие API-ответов ≥1 КБ (списки товаров/спеков
#    сжимаются в 5–10 раз; XLSX/ZIP уже сжаты и повторно не жмутся)
# ============================================================
app.add_middleware(GZipMiddleware, minimum_size=1024)


# ============================================================
# 3. SlowAPI — глобальный rate-limit
# ============================================================
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ============================================================
# 4. CORS — САМЫЙ ВНЕШНИЙ middleware (добавляется последним)
# ============================================================
# Было Н-1 из код-ревью: dev-origins (localhost:5173/3000) попадали в
# CORS всегда, включая production, вместе с allow_credentials=True.
# Теперь dev-origins добавляются ТОЛЬКО вне production; в проде список
# строится исключительно из settings.CORS_ORIGINS.


def _build_cors_origins(*, is_production: bool, configured: list[str]) -> list[str]:
    """Разрешённые CORS-origins.

    Вне production к настроенным origins добавляются локальные dev-адреса
    (Vite 5173 и альтернативный 3000). В production — только явные
    settings.CORS_ORIGINS. Дубликаты схлопываются, порядок сохраняется.
    """
    local_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    if is_production:
        return list(dict.fromkeys(configured))
    return list(dict.fromkeys(local_origins + configured))


config_origins = []
if hasattr(settings, "CORS_ORIGINS") and settings.CORS_ORIGINS:
    if isinstance(settings.CORS_ORIGINS, str):
        config_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    else:
        config_origins = list(settings.CORS_ORIGINS)

allowed_origins = _build_cors_origins(is_production=_IS_PRODUCTION, configured=config_origins)

if _IS_PRODUCTION and not allowed_origins:
    logger.warning(
        "CORS_ORIGINS не задан в production: кросс-доменные запросы с "
        "credentials будут отклоняться (штатно, если фронт и API живут "
        "на одном домене за reverse-proxy)"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Роутеры
# ============================================================
app.include_router(health_router)
app.include_router(migrate_router)
app.include_router(variants.router)
app.include_router(stats.router)
app.include_router(attributes.router)
app.include_router(photos.router)
app.include_router(templates.router)
app.include_router(products.router)
app.include_router(import_router.router)
app.include_router(export.router)
app.include_router(auth.router)
app.include_router(email_router.router)
app.include_router(media_router.router)
app.include_router(categories.router)
app.include_router(history.router)
app.include_router(defaults_router.router)
app.include_router(tnved.router)
app.include_router(profiles.router)  # профили миграции (площадка + дефолты)

# ============================================================
# Статика: раздача скачанных фото
# ============================================================
MEDIA_DIR = Path(__file__).parent / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
# /media раздаёт routers/media.py с авторизацией (владелец/админ),
# а nginx проксирует /media на backend (см. deploy/nginx/conf.d)


# ============================================================
# Служебные эндпоинты
# ============================================================
@app.get("/api/platforms")
def get_platforms():
    """Получить список доступных платформ.

    R-35 (В-14): итерируем по общему ключу — раньше PLATFORM_CONFIG[p.value]
    падал бы с KeyError при любом расхождении enum и реестра. Пары без
    конфигурации не показываются; сам рассинхрон ловит тест реестра
    (tests/test_platform_registry.py), требующий полного совпадения
    ключей Platform / PLATFORM_CONFIG / PRICE_RULES.
    """
    return {
        "platforms": [
            {
                "id": p.value,
                "name": cfg["name"],
                "color": cfg["color"],
            }
            for p in Platform
            if (cfg := PLATFORM_CONFIG.get(p.value)) is not None
        ]
    }


@app.get("/")
def root():
    """Корневой эндпоинт"""
    return {
        "message": "Marketplace Migrator API v3.4 (Rate-limited)",
        "platforms": Platform.all_values(),
        "docs": "/docs" if not _IS_PRODUCTION else "disabled",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
