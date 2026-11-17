"""
Конфигурация приложения.

Все секреты и параметры окружения читаются из переменных окружения
и файла .env через pydantic-settings. В коде секретов НЕТ.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)

# Заглушка ТОЛЬКО для разработки. В production с ней запуск невозможен.
DEV_SECRET_FALLBACK = "dev-only-insecure-key-change-me"

# Маркер-плейсхолдер из .env.example. Скопированный «как есть» файл .env.example
# не должен молча становиться рабочей конфигурацией (R-35 из код-ревью):
# раньше JWT_SECRET=CHANGE_ME__… проходил все проверки — значение не равно
# DEV_SECRET_FALLBACK, и прод поднимался с плейсхолдером в качестве секрета.
PLACEHOLDER_MARK = "CHANGE_ME"


class Settings(BaseSettings):
    """Настройки приложения. Приоритет: env-переменные > .env > дефолты.
    Все поля в UPPERCASE, чтобы совпадать с .env и обращениями в коде."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),  # ищем в backend/ и в корне проекта
        env_file_encoding="utf-8",
        case_sensitive=False,  # для env-чтения регистр не важен
        extra="ignore",  # игнорируем лишние переменные из .env
    )

    # --- Окружение ---
    ENVIRONMENT: str = "development"  # development | production

    # --- Куки аутентификации ---
    # Secure-флаг: включать ТОЛЬКО после настройки HTTPS (иначе браузер не примет куку по HTTP)
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    # --- Безопасность (секреты) ---
    SECRET_KEY: str = DEV_SECRET_FALLBACK
    JWT_SECRET: str = ""  # алиас для совместимости с .env.example и docker-compose.prod.yml
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 часа

    # --- База данных ---
    DATABASE_URL: str = ""  # пусто -> sqlite-fallback для разработки
    POSTGRES_USER: str = "migrator_user"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "marketplace_migrator"
    # R-35 (В-10 ревью): бюджет соединений. Раньше каждый из двух движков
    # держал 10+20: до 60 соединений на процесс, 3 uvicorn-воркера в проде
    # + celery-воркеры → гарантированное исчерпание max_connections=100.
    # Дефолты ужаты (бюджет — комментарий в database/session.py).
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # --- Логирование ---
    # R-35 (В-12): уровень для configure_logging() (core/logging_config.py)
    LOG_LEVEL: str = "INFO"

    # --- Redis (Celery + rate-limit) ---
    REDIS_URL: str = "redis://redis:6379/0"

    # --- Email (SMTP) ---
    SMTP_ENABLED: bool = False
    EMAIL_VERIFICATION_REQUIRED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Marketplace Migrator"
    SMTP_TLS: bool = True

    # --- Базовый URL для ссылок в письмах и статики ---
    PUBLIC_URL: str = "http://localhost:5173"

    # --- Домен ---
    APP_DOMAIN: str = ""

    # --- CORS (all-eating: JSON-массив или CSV) ---
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v):
        """Принимает:
        - Python list (из тестов)
        - JSON-массив: '["https://a.ru","http://b.ru"]'
        - CSV-строку: 'https://a.ru,http://b.ru'
        - пустую строку → []
        """
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                    return parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    return []
            return [x.strip() for x in v.split(",") if x.strip()]
        return []

    # --- Sentry (опционально) ---
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_RELEASE: str = "local"

    # --- Ключи маркетплейсов (серверный fallback для загрузки спеков) ---
    OZON_CLIENT_ID: str = ""
    OZON_API_KEY: str = ""

    # --- Шифрование чувствительных данных ---
    FERNET_KEY: str = ""

    # --- Админ-бутстрап (опционально) ---
    ADMIN_USERNAME: str = ""
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # --- Пути ---
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    @property
    def photos_dir(self) -> Path:
        return self.BASE_DIR / "photos"

    @property
    def media_dir(self) -> Path:
        return self.BASE_DIR / "media"

    @property
    def data_dir(self) -> Path:
        return self.BASE_DIR / "data"

    @property
    def resolved_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"sqlite:///{self.BASE_DIR / 'migrator.db'}"

    @model_validator(mode="after")
    def _ensure_secret_is_set(self) -> "Settings":
        """Унифицируем SECRET_KEY и JWT_SECRET; проверяем секреты (R-35)."""
        if self.SECRET_KEY == DEV_SECRET_FALLBACK and self.JWT_SECRET:
            self.SECRET_KEY = self.JWT_SECRET

        # 1) Плейсхолдеры CHANGE_ME из .env.example — сам маркер независимо
        #    от того, в каком из полей он оказался
        with_placeholder = [
            name
            for name, value in (
                ("SECRET_KEY", self.SECRET_KEY),
                ("JWT_SECRET", self.JWT_SECRET),
                ("DATABASE_URL", self.DATABASE_URL),
                ("ADMIN_PASSWORD", self.ADMIN_PASSWORD),
            )
            if PLACEHOLDER_MARK in (value or "")
        ]
        if with_placeholder:
            msg = (
                "Обнаружены ненастоящие значения из .env.example (CHANGE_ME): "
                + ", ".join(with_placeholder)
                + '. Сгенерируйте реальные: python -c "import secrets; print(secrets.token_hex(32))"'
            )
            if self.ENVIRONMENT == "production":
                raise ValueError(msg)
            logger.warning(msg)

        # 2) Подсказка на типовую ошибку compose: БД создаётся с POSTGRES_PASSWORD,
        #    а бэкенд подключается по паролю из DATABASE_URL — при рассинхроне
        #    подключение падает на runtime невнятной ошибкой аутентификации
        if self.DATABASE_URL and self.POSTGRES_PASSWORD:
            db_password = urlparse(self.DATABASE_URL).password or ""
            if db_password and db_password != self.POSTGRES_PASSWORD:
                logger.warning(
                    "Пароль в DATABASE_URL не совпадает с POSTGRES_PASSWORD — "
                    "подключение к БД, создаваемой docker compose, завершится "
                    "ошибкой аутентификации."
                )

        if self.ENVIRONMENT == "production" and self.SECRET_KEY == DEV_SECRET_FALLBACK:
            raise ValueError(
                "ENVIRONMENT=production, но SECRET_KEY (или JWT_SECRET) не задан. "
                "Укажите SECRET_KEY в .env или переменной окружения."
            )
        if self.SECRET_KEY == DEV_SECRET_FALLBACK:
            logger.warning("⚠️ Используется DEV-значение SECRET_KEY. Задайте SECRET_KEY в .env!")
        return self


@lru_cache
def get_settings() -> Settings:
    """Singleton настроек."""
    return Settings()


settings = get_settings()

# Директории создаём при старте
settings.photos_dir.mkdir(parents=True, exist_ok=True)
settings.media_dir.mkdir(parents=True, exist_ok=True)
settings.data_dir.mkdir(parents=True, exist_ok=True)

# --- Обратная совместимость ---
BASE_DIR = settings.BASE_DIR
PHOTOS_DIR = settings.photos_dir
MEDIA_DIR = settings.media_dir
DATA_DIR = settings.data_dir
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
DATABASE_URL = settings.resolved_database_url
