"""
Централизованный обработчик ошибок FastAPI.
Все исключения ловятся здесь и возвращаются в едином формате.
"""

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from core.exceptions import AppException

logger = logging.getLogger(__name__)


def format_error_response(
    status_code: int,
    message: str,
    error_code: str = "INTERNAL_ERROR",
    details: dict = None,
) -> dict:
    """Единый формат ответа об ошибке."""
    return {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {},
        },
    }


async def app_exception_handler(request: Request, exc: AppException):
    """Обработчик кастомных исключений приложения."""
    logger.warning(
        f"AppException: {exc.error_code} — {exc.message}",
        extra={"path": request.url.path, "method": request.method},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(
            status_code=exc.status_code,
            message=exc.message,
            error_code=exc.error_code,
            details=exc.details,
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Обработчик стандартных HTTPException."""
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(
            status_code=exc.status_code,
            message=exc.detail,
            error_code="HTTP_ERROR",
        ),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Обработчик ошибок валидации Pydantic."""
    errors = exc.errors()
    human_errors = []
    for err in errors:
        loc = " → ".join(str(part) for part in err["loc"] if part != "body")
        human_errors.append(
            {
                "field": loc or "body",
                "message": err["msg"],
                "type": err["type"],
            }
        )

    logger.warning(f"Validation error on {request.url.path}: {human_errors}")
    return JSONResponse(
        status_code=422,
        content=format_error_response(
            status_code=422,
            message="Ошибка валидации входных данных",
            error_code="VALIDATION_ERROR",
            details={"fields": human_errors},
        ),
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Обработчик ошибок БД — скрываем детали от клиента."""
    logger.exception(f"Database error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content=format_error_response(
            status_code=500,
            message="Внутренняя ошибка сервера базы данных",
            error_code="DATABASE_ERROR",
        ),
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """Фолбэк для всех необработанных исключений."""
    logger.exception(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content=format_error_response(
            status_code=500,
            message="Внутренняя ошибка сервера",
            error_code="INTERNAL_ERROR",
        ),
    )


def register_exception_handlers(app):
    """Регистрирует все обработчики в FastAPI приложении."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
