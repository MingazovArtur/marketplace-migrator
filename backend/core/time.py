"""Единая точка времени в приложении.

Исторически весь проект пишет в БД naive-UTC (datetime.utcnow()).
Колонки Postgres объявлены как TIMESTAMP WITHOUT TIME ZONE, поэтому
переход на aware datetime.now(UTC) без .replace(tzinfo=None) менял бы
семантику записи (psycopg2 конвертирует aware-значения через TimeZone
сессии). Хелпер ниже сохраняет старую семантику, убирая deprecation.
"""
from datetime import UTC, datetime


def utcnow() -> datetime:
    """Naive UTC «сейчас» — замена datetime.utcnow() без DeprecationWarning."""
    return datetime.now(UTC).replace(tzinfo=None)
