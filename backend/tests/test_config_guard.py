"""Тесты гейта плейсхолдеров CHANGE_ME и сверки паролей БД (R-35).

Раньше JWT_SECRET=CHANGE_ME__… из скопированного «как есть» .env.example
проходил все проверки config.py (значение не равно DEV_SECRET_FALLBACK),
и прод поднимался с плейсхолдером в качестве секрета подписи.

Стиль проекта: чистые юнит-тесты — Settings собирается с явными kwargs
поверх тестового окружения из conftest (env > .env > дефолты < kwargs).
"""

import logging

import pytest

from core.config import Settings


def test_change_me_jwt_secret_in_production_raises():
    """Скопированный как есть .env.example не стартует в production."""
    with pytest.raises(ValueError, match="CHANGE_ME"):
        Settings(ENVIRONMENT="production", JWT_SECRET="CHANGE_ME__python_-c_x")


def test_change_me_database_url_in_production_raises():
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql+psycopg2://u:CHANGE_ME@db:5432/x",
        )


def test_change_me_admin_password_in_production_raises():
    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        Settings(ENVIRONMENT="production", ADMIN_PASSWORD="CHANGE_ME__x")


def test_change_me_in_dev_only_warns(caplog):
    """Вне production плейсхолдеры — предупреждение, а не отказ запуска."""
    with caplog.at_level(logging.WARNING, logger="core.config"):
        Settings(ENVIRONMENT="development", JWT_SECRET="CHANGE_ME__x")
    assert "CHANGE_ME" in caplog.text
    assert "JWT_SECRET" in caplog.text


def test_clean_config_has_no_placeholder_warnings(caplog):
    with caplog.at_level(logging.WARNING, logger="core.config"):
        Settings(
            ENVIRONMENT="development",
            JWT_SECRET="real-secret-token-hex-32-bytes",
            DATABASE_URL="postgresql+psycopg2://u:realpass@db:5432/x",
            POSTGRES_PASSWORD="realpass",
        )
    assert "CHANGE_ME" not in caplog.text


def test_password_mismatch_warns(caplog):
    """Пароль в DATABASE_URL != POSTGRES_PASSWORD — предупреждение о runtime-отказе."""
    with caplog.at_level(logging.WARNING, logger="core.config"):
        Settings(
            ENVIRONMENT="development",
            JWT_SECRET="real-secret",
            DATABASE_URL="postgresql+psycopg2://u:p1@db:5432/x",
            POSTGRES_PASSWORD="p2",
        )
    assert "POSTGRES_PASSWORD" in caplog.text
    assert "CHANGE_ME" not in caplog.text


def test_matching_passwords_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="core.config"):
        Settings(
            ENVIRONMENT="development",
            JWT_SECRET="real-secret",
            DATABASE_URL="postgresql+psycopg2://u:realpass@db:5432/x",
            POSTGRES_PASSWORD="realpass",
        )
    assert "POSTGRES_PASSWORD" not in caplog.text
