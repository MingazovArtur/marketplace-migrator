"""
Главный файл приложения FastAPI

Порядок обработки запроса (от внешнего к внутреннему):
  Запрос → CORS (самый внешний) → SlowAPI → ban_check → роутер
"""

import logging
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core.config import settings
from core.error_handler import register_exception_handlers
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
    defaults as defaults_router,
    email_router,
    export,
    history,
    import_router,
    media as media_router,  # ✅ /media с авторизацией (замена StaticFiles)
    photos,  # ✅ ИСПРАВЛЕНО: подключен роутер фотографий
    profiles,  # ✅ v4: профили миграции (площадка + дефолты)
    products,
    stats,
    templates,
    tnved,
    variants,
)
from routers.health import router as health_router
from routers.migrate_router import router as migrate_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    """
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path

    if path in ("/api/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)

    ip = get_client_ip(request)
    if is_banned(f"ip:{ip}"):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Доступ временно ограничен из-за подозрительной активности"},
        )

    try:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            from core.auth import decode_token

            payload = decode_token(token)
            if payload and "sub" in payload:
                user_id = str(payload["sub"])
                if is_banned(f"user:{user_id}"):
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Ваш аккаунт временно заблокирован"},
                    )
    except Exception as e:
        logger.debug(f"ban_check token parse failed: {e}")

    response = await call_next(request)
    return response


# ============================================================
# 2. SlowAPI — глобальный rate-limit
# ============================================================
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ============================================================
# 3. CORS — САМЫЙ ВНЕШНИЙ middleware (добавляется последним)
# ============================================================
local_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

config_origins = []
if hasattr(settings, "CORS_ORIGINS") and settings.CORS_ORIGINS:
    if isinstance(settings.CORS_ORIGINS, str):
        config_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    else:
        config_origins = list(settings.CORS_ORIGINS)

allowed_origins = list(set(local_origins + config_origins))

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
app.include_router(photos.router)  # ✅ ИСПРАВЛЕНО: подключен роутер фотографий
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
app.include_router(profiles.router)  # ✅ v4: профили миграции

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
    """Получить список доступных платформ"""
    return {
        "platforms": [
            {
                "id": p.value,
                "name": PLATFORM_CONFIG[p.value]["name"],
                "color": PLATFORM_CONFIG[p.value]["color"],
            }
            for p in Platform
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