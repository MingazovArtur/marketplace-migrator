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

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)

# Заглушка ТОЛЬКО для разработки. В production с ней запуск невозможен.
DEV_SECRET_FALLBACK = "dev-only-insecure-key-change-me"


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
        """Унифицируем SECRET_KEY и JWT_SECRET; проверяем наличие ключа в production."""
        if self.SECRET_KEY == DEV_SECRET_FALLBACK and self.JWT_SECRET:
            self.SECRET_KEY = self.JWT_SECRET

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