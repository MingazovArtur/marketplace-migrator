"""
Сервис кэширования на базе Redis.
Используется для снижения нагрузки на БД при частых запросах (спеки, категории).
✅ v2: Функции вынесены на уровень модуля для прямого вызова через cache_service.get()
"""

import json
import logging
from typing import Any

import redis

from core.config import settings

logger = logging.getLogger(__name__)

# Инициализация клиента Redis с проверкой подключения
try:
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("✅ Redis подключен успешно для кэширования")
except redis.ConnectionError as e:
    logger.error(
        f"❌ Ошибка подключения к Redis: {e}. Кэширование отключено (будет использоваться БД)."
    )
    redis_client = None


def get(key: str) -> Any | None:
    """Получить значение из кэша. Возвращает распарсенный JSON или None."""
    if not redis_client:
        return None
    try:
        val = redis_client.get(key)
        if val:
            return json.loads(val)
    except Exception as e:
        logger.warning(f"Ошибка чтения из кэша {key}: {e}")
    return None


def set(key: str, value: Any, ttl: int = 3600) -> bool:
    """Сохранить значение в кэш с TTL (по умолчанию 1 час)."""
    if not redis_client:
        return False
    try:
        redis_client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        return True
    except Exception as e:
        logger.warning(f"Ошибка записи в кэш {key}: {e}")
        return False


def delete_pattern(pattern: str) -> bool:
    """
    Удаляет все ключи, соответствующие паттерну (например, 'specs:ozon:*').
    Использует scan_iter, который безопасен для production (не блокирует Redis, в отличие от KEYS).
    """
    if not redis_client:
        return False
    try:
        keys = redis_client.scan_iter(pattern)
        pipe = redis_client.pipeline()
        for key in keys:
            pipe.delete(key)
        pipe.execute()
        logger.info(f"🧹 Очищен кэш по паттерну: {pattern}")
        return True
    except Exception as e:
        logger.warning(f"Ошибка удаления кэша по паттерну {pattern}: {e}")
        return False
