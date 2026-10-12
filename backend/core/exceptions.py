"""
Кастомные исключения приложения.
Единый формат ошибок для всего API.
"""

from typing import Any


class AppException(Exception):
    """Базовое исключение приложения."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class ValidationError(AppException):
    """Ошибка валидации входных данных."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class NotFoundError(AppException):
    """Ресурс не найден."""

    def __init__(self, message: str = "Ресурс не найден"):
        super().__init__(
            message=message,
            status_code=404,
            error_code="NOT_FOUND",
        )


class AuthenticationError(AppException):
    """Ошибка аутентификации."""

    def __init__(self, message: str = "Не авторизован"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_ERROR",
        )


class ForbiddenError(AppException):
    """Доступ запрещён."""

    def __init__(self, message: str = "Доступ запрещён"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="FORBIDDEN",
        )


class ExternalAPIError(AppException):
    """Ошибка внешнего API (Ozon, WB, Яндекс)."""

    def __init__(self, message: str, platform: str, status_code: int = 502):
        super().__init__(
            message=f"Ошибка {platform}: {message}",
            status_code=status_code,
            error_code="EXTERNAL_API_ERROR",
            details={"platform": platform},
        )


class ExportError(AppException):
    """Ошибка экспорта."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code="EXPORT_ERROR",
            details=details,
        )


class ImportError(AppException):
    """Ошибка импорта."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code="IMPORT_ERROR",
            details=details,
        )
