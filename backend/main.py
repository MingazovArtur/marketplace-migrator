"""
Главный файл приложения FastAPI
"""
import logging
from pathlib import Path
from routers import import_router
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from routers import email_router
from core.config import settings
from core.platforms import Platform, PLATFORM_CONFIG
from core.rate_limit import (
    limiter,
    rate_limit_exceeded_handler,
    is_banned,
    get_client_ip,
)
from routers import (
    products,
    import_router,
    export,
    auth,
    categories,
    templates,
    history,
    attributes,
    variants,
    stats,
)
from routers.migrate_router import router as migrate_router
from routers.health import router as health_router


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Marketplace Migrator API", version="3.4")
app.include_router(import_router.router)

# ============================================================
# 1. CORS — берём origins из settings.CORS_ORIGINS (из .env)
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 2. SlowAPI — глобальный rate-limit + обработчик превышений
# ============================================================
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Глобальный лимит: 100 req/min на идентификатор для всех не-декорированных эндпоинтов
# (эндпоинты с @limiter.limit(...) имеют свои, более строгие лимиты)
app.add_middleware(SlowAPIMiddleware, default_limits=["100/minute"])


# ============================================================
# 3. Ban-check middleware — отсекает забаненных ДО обработки
# ============================================================
# FastAPI применяет middleware в обратном порядке, поэтому добавляем последним
@app.middleware("http")
async def ban_check_middleware(request: Request, call_next):
    """
    Проверяет бан IP и user_id перед обработкой запроса.
    Исключения: healthcheck (/api/health), статика (/media), docs.
    """
    path = request.url.path

    # Пропускаем эндпоинты мониторинга и статику
    if path in ("/api/health", "/docs", "/openapi.json", "/redoc") or path.startswith("/media"):
        return await call_next(request)

    # Проверка бана IP
    ip = get_client_ip(request)
    if is_banned(f"ip:{ip}"):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Доступ временно ограничен из-за подозрительной активности"},
        )

    # Проверка бана user_id (если авторизован)
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
        # Ошибка декодирования токена — не наша забота здесь, пропустим
        pass

    response = await call_next(request)
    return response


# ============================================================
# 4. Роутеры
# ============================================================
app.include_router(health_router)
app.include_router(migrate_router)      # единственный импорт migrate
app.include_router(variants.router)
app.include_router(stats.router)
app.include_router(attributes.router)
app.include_router(templates.router)
app.include_router(products.router)
app.include_router(import_router.router)
app.include_router(export.router)
app.include_router(auth.router)
app.include_router(email_router.router)
app.include_router(categories.router)
app.include_router(history.router)


# ============================================================
# 5. Статика: раздача скачанных фото
# ============================================================
MEDIA_DIR = Path(__file__).parent / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


# ============================================================
# 6. Служебные эндпоинты
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
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)