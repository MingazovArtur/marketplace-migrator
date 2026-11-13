"""Класс CategoryService и глобальный синглтон category_service.

Оркестрация: кэш в памяти → БД → API площадки → встроенные заглушки.
Хранение — в _storage, загрузка из API — в _api_loaders, заглушки — в _mocks.
Вынесено без изменений из монолита services/category_service.py (Р6).
"""

import logging

import httpx

from services.category_service._api_loaders import load_categories_from_api
from services.category_service._mocks import get_mock_categories
from services.category_service._storage import (
    find_category_mapping,
    find_mapping_for_product,
    load_categories_from_db,
    save_categories_to_db,
    upsert_category_mapping,
)

logger = logging.getLogger(__name__)


class CategoryService:
    """Сервис для управления справочниками категорий.

    Поддерживает два режима работы:
    1. Встроенные справочники (заглушки) — работают без API-ключей
    2. Реальные API — при передаче валидного ключа загружаются актуальные данные
    """

    def __init__(self):
        self._cache = {}  # Кэш категорий по платформам

    # =====================================================================
    # ПУБЛИЧНЫЕ МЕТОДЫ
    # =====================================================================

    def get_categories(self, platform: str, force_refresh: bool = False) -> list[dict]:
        """
        Получить список категорий для платформы.
        Использует кэш → БД → заглушки.
        """
        cache_key = platform

        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]

        # Пытаемся получить из БД
        categories = load_categories_from_db(platform)
        if categories:
            self._cache[cache_key] = categories
            return categories

        # Если в БД нет — используем встроенные заглушки
        categories_data = get_mock_categories(platform)
        save_categories_to_db(platform, categories_data)
        self._cache[cache_key] = categories_data
        return categories_data

    def get_categories_with_api_key(self, platform: str, api_key: str) -> list[dict]:
        """
        Получить категории с использованием реального API ключа.
        При ошибке API — автоматически fallback на встроенные справочники.
        """
        if not api_key or not api_key.strip():
            return self.get_categories(platform)

        try:
            categories_data = load_categories_from_api(platform, api_key)

            if categories_data:
                # Сохраняем в БД и обновляем кэш
                save_categories_to_db(platform, categories_data)
                self._cache[platform] = categories_data
                logger.info(f"✅ Загружено {len(categories_data)} категорий из API для {platform}")
                return categories_data

            # API вернул пустой результат — используем заглушки
            logger.warning(f"API вернул пустой результат для {platform}, используем заглушки")
            return self.get_categories(platform)

        except httpx.HTTPError as e:
            logger.warning(f"Не удалось подключиться к API {platform}: {e}. Используем заглушки.")
            return self.get_categories(platform)
        except Exception as e:
            logger.error(
                f"Ошибка при загрузке категорий из API {platform}: {e}. Используем заглушки."
            )
            return self.get_categories(platform)

    def get_category_mapping(
        self,
        source_platform: str,
        source_category_id: str,
        target_platform: str,
        user_id: int | None = None,
    ) -> dict | None:
        """Найти сохраненный маппинг категории"""
        return find_category_mapping(
            source_platform, source_category_id, target_platform, user_id=user_id
        )

    def save_category_mapping(
        self,
        user_id: int,
        source_platform: str,
        source_category_id: str,
        target_platform: str,
        target_category_id: str,
        is_manual: bool = True,
    ) -> dict:
        """Сохранить маппинг категории"""
        return upsert_category_mapping(
            user_id,
            source_platform,
            source_category_id,
            target_platform,
            target_category_id,
            is_manual=is_manual,
        )

    def get_mapping_for_product(
        self, source_platform: str, category_name: str, target_platform: str, user_id: int
    ) -> dict | None:
        """Найти маппинг для товара по имени категории."""
        return find_mapping_for_product(source_platform, category_name, target_platform, user_id)


# Глобальный экземпляр
category_service = CategoryService()
