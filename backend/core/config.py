from pathlib import Path
import os

BASE_DIR = Path(__file__).parent.parent
PHOTOS_DIR = BASE_DIR / "photos"
DATA_DIR = BASE_DIR / "data"

# Создаем директории при старте, если их нет
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# JWT настройки
SECRET_KEY = "your-super-secret-key-change-in-production-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 часа

# URL базы данных (из переменной окружения для Docker)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR}/migrator.db"
)