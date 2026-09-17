"""
Конфигурация приложения.

Все секреты и параметры окружения читаются из переменных окружения
и файла .env через pydantic-settings. В коде секретов НЕТ.
"""
import logging
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Заглушка ТОЛЬКО для разработки. В production с ней запуск невозможен.
DEV_SECRET_FALLBACK = "dev-only-insecure-key-change-me"


class Settings(BaseSettings):
    """Настройки приложения. Приоритет: env-переменные > .env > дефолты."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),  # ищем в backend/ и в корне проекта
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Окружение ---
    environment: str = "development"  # development | production

    # --- Безопасность (секреты) ---
    secret_key: str = DEV_SECRET_FALLBACK
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 часа

    # --- База данных ---
    database_url: str = ""  # пусто -> sqlite-fallback для разработки

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Пути ---
    base_dir: Path = Path(__file__).resolve().parent.parent

    @property
    def photos_dir(self) -> Path:
        return self.base_dir / "photos"

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.base_dir / 'migrator.db'}"

    @model_validator(mode="after")
    def _ensure_secret_is_set(self) -> "Settings":
        """Не даём запустить production без настоящего SECRET_KEY."""
        if self.environment == "production" and self.secret_key == DEV_SECRET_FALLBACK:
            raise ValueError(
                "ENVIRONMENT=production, но SECRET_KEY не задан. "
                "Укажите SECRET_KEY в .env или переменной окружения."
            )
        if self.secret_key == DEV_SECRET_FALLBACK:
            logger.warning("⚠️ Используется DEV-значение SECRET_KEY. Задайте SECRET_KEY в .env!")
        return self


@lru_cache
def get_settings() -> Settings:
    """Singleton настроек."""
    return Settings()


settings = get_settings()

# Директории создаём при старте (как раньше)
settings.photos_dir.mkdir(parents=True, exist_ok=True)
settings.data_dir.mkdir(parents=True, exist_ok=True)

# --- Обратная совместимость ---
# Старые импорты вида `from core.config import SECRET_KEY, DATABASE_URL`
# продолжают работать без правок auth.py / session.py.
BASE_DIR = settings.base_dir
PHOTOS_DIR = settings.photos_dir
DATA_DIR = settings.data_dir
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
DATABASE_URL = settings.resolved_database_url