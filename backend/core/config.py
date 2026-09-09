from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
PHOTOS_DIR = BASE_DIR / "photos"
DATA_DIR = BASE_DIR / "data"

# Создаем директории при старте, если их нет
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)