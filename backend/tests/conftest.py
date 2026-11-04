"""Общие настройки тестов backend.

Запуск из корня репозитория:  pytest backend/tests
Запуск из backend/:           pytest tests

conftest ДО импорта модулей приложения выставляет минимальное окружение,
чтобы тесты не требовали реальную БД/Redis (используются только чистые
функции, стабы и monkeypatch).
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Окружение для тестов — задаём ЖЁСТКО (не setdefault), чтобы тесты не зависели
# от случайных переменных машины разработителя/CI
os.environ["DATABASE_URL"] = "postgresql+psycopg2://test:test@localhost:5432/test"
os.environ["SECRET_KEY"] = "test-secret-key-for-ci-only"
os.environ["ENVIRONMENT"] = "test"
