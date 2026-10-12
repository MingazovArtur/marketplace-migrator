"""
Сервис для работы со справочниками категорий маркетплейсов.

Поддерживает два режима работы:
1. Встроенные справочники (заглушки) — работают без API-ключей
2. Реальные API — при передаче валидного ключа загружаются актуальные данные
"""

import logging

import requests

from database.models import Category, CategoryMapping
from database.session import SessionLocal

logger = logging.getLogger(__name__)


class CategoryService:
    """Сервис для управления справочниками категорий"""

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
        db = SessionLocal()
        try:
            categories = (
                db.query(Category)
                .filter(Category.platform == platform, Category.is_active == True)
                .all()
            )

            if categories:
                result = [
                    {
                        "id": c.category_id,
                        "name": c.name,
                        "parent_id": c.parent_id,
                        "full_path": c.full_path,
                        "level": c.level,
                    }
                    for c in categories
                ]
                self._cache[cache_key] = result
                return result
        finally:
            db.close()

        # Если в БД нет — используем встроенные заглушки
        categories_data = self._get_mock_categories(platform)
        self._save_categories_to_db(platform, categories_data)
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
            categories_data = self._load_categories_from_api(platform, api_key)

            if categories_data:
                # Сохраняем в БД и обновляем кэш
                self._save_categories_to_db(platform, categories_data)
                self._cache[platform] = categories_data
                logger.info(f"✅ Загружено {len(categories_data)} категорий из API для {platform}")
                return categories_data

            # API вернул пустой результат — используем заглушки
            logger.warning(f"API вернул пустой результат для {platform}, используем заглушки")
            return self.get_categories(platform)

        except requests.exceptions.RequestException as e:
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
        db = SessionLocal()
        try:
            query = db.query(CategoryMapping).filter(
                CategoryMapping.source_platform == source_platform,
                CategoryMapping.source_category_id == source_category_id,
                CategoryMapping.target_platform == target_platform,
            )

            if user_id:
                query = query.filter(CategoryMapping.user_id == user_id)

            mapping = query.first()

            if mapping:
                return {
                    "target_category_id": mapping.target_category_id,
                    "confidence": mapping.confidence,
                    "is_manual": mapping.is_manual,
                }

            return None
        finally:
            db.close()

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
        db = SessionLocal()
        try:
            existing = (
                db.query(CategoryMapping)
                .filter(
                    CategoryMapping.user_id == user_id,
                    CategoryMapping.source_platform == source_platform,
                    CategoryMapping.source_category_id == source_category_id,
                    CategoryMapping.target_platform == target_platform,
                )
                .first()
            )

            if existing:
                existing.target_category_id = target_category_id
                existing.is_manual = is_manual
                existing.confidence = 1.0
            else:
                new_mapping = CategoryMapping(
                    user_id=user_id,
                    source_platform=source_platform,
                    source_category_id=source_category_id,
                    target_platform=target_platform,
                    target_category_id=target_category_id,
                    is_manual=is_manual,
                    confidence=1.0,
                )
                db.add(new_mapping)

            db.commit()

            return {
                "success": True,
                "source": f"{source_platform}:{source_category_id}",
                "target": f"{target_platform}:{target_category_id}",
            }
        except Exception as e:
            db.rollback()
            return {"success": False, "error": str(e)}
        finally:
            db.close()

    # =====================================================================
    # ЗАГРУЗКА ИЗ РЕАЛЬНЫХ API
    # =====================================================================

    def _load_categories_from_api(self, platform: str, api_key: str) -> list[dict] | None:
        """
        Загрузка реальных категорий из API площадки.
        Возвращает None при ошибке.
        """
        if not api_key:
            return None

        try:
            if platform == "ozon":
                return self._load_ozon_categories(api_key)
            elif platform == "wildberries":
                return self._load_wildberries_categories(api_key)
            elif platform == "yandex":
                return self._load_yandex_categories(api_key)
        except Exception as e:
            logger.error(f"Ошибка загрузки категорий из API {platform}: {e}")
            return None

        return None

    def _load_ozon_categories(self, api_key: str) -> list[dict] | None:
        """Загрузка категорий из Ozon Seller API"""
        client_id, api_key_val = api_key.split(":") if ":" in api_key else (api_key, api_key)

        response = requests.post(
            "https://api-seller.ozon.ru/v1/description-category/tree",
            headers={
                "Client-Id": client_id,
                "Api-Key": api_key_val,
                "Content-Type": "application/json",
            },
            json={"language": "DEFAULT"},
            timeout=10,
        )

        if response.status_code == 200:
            raw = response.json().get("result", [])
            return [
                {
                    "id": str(cat["id"]),
                    "name": cat["name"],
                    "parent_id": str(cat["parent_id"]) if cat.get("parent_id") else None,
                    "full_path": None,
                    "level": 0,
                }
                for cat in raw
                if not cat.get("disabled", False)
            ]

        logger.warning(f"Ozon API вернул статус {response.status_code}")
        return None

    def _load_wildberries_categories(self, api_key: str) -> list[dict] | None:
        """Загрузка категорий из WB Content API"""
        response = requests.get(
            "https://content.wildberries.ru/content/v2/object/all",
            headers={"Authorization": api_key},
            timeout=10,
        )

        if response.status_code == 200:
            raw = response.json()
            return [
                {
                    "id": str(subj["subjectId"]),
                    "name": subj["subjectName"],
                    "parent_id": (
                        str(subj.get("parentSubjectId")) if subj.get("parentSubjectId") else None
                    ),
                    "full_path": None,
                    "level": 0,
                }
                for subj in raw
            ]

        logger.warning(f"WB API вернул статус {response.status_code}")
        return None

    def _load_yandex_categories(self, api_key: str) -> list[dict] | None:
        """Загрузка категорий из Yandex Business API"""
        token, campaign_id = api_key.split(":") if ":" in api_key else (api_key, "")

        response = requests.get(
            "https://api.partner.market.yandex.ru/v2/categories",
            headers={"Authorization": f"OAuth {token}"},
            params={"campaignId": campaign_id},
            timeout=10,
        )

        if response.status_code == 200:
            raw = response.json().get("categories", [])
            return [
                {
                    "id": str(cat["id"]),
                    "name": cat["name"],
                    "parent_id": str(cat["parentId"]) if cat.get("parentId") else None,
                    "full_path": None,
                    "level": 0,
                }
                for cat in raw
            ]

        logger.warning(f"Yandex API вернул статус {response.status_code}")
        return None

    # =====================================================================
    # ВСТРОЕННЫЕ СПРАВОЧНИКИ (ЗАГЛУШКИ)
    # =====================================================================

    def _get_mock_categories(self, platform: str) -> list[dict]:
        """Встроенные справочники категорий (используются при отсутствии API-ключа)"""
        mock_categories = {
            "ozon": [
                {
                    "id": "1",
                    "name": "Электроника",
                    "parent_id": None,
                    "full_path": "Электроника",
                    "level": 0,
                },
                {
                    "id": "101",
                    "name": "Смартфоны",
                    "parent_id": "1",
                    "full_path": "Электроника > Смартфоны",
                    "level": 1,
                },
                {
                    "id": "102",
                    "name": "Ноутбуки",
                    "parent_id": "1",
                    "full_path": "Электроника > Ноутбуки",
                    "level": 1,
                },
                {
                    "id": "103",
                    "name": "Аудиотехника",
                    "parent_id": "1",
                    "full_path": "Электроника > Аудиотехника",
                    "level": 1,
                },
                {
                    "id": "1031",
                    "name": "Наушники",
                    "parent_id": "103",
                    "full_path": "Электроника > Аудиотехника > Наушники",
                    "level": 2,
                },
                {
                    "id": "2",
                    "name": "Дом и сад",
                    "parent_id": None,
                    "full_path": "Дом и сад",
                    "level": 0,
                },
                {
                    "id": "201",
                    "name": "Уборка",
                    "parent_id": "2",
                    "full_path": "Дом и сад > Уборка",
                    "level": 1,
                },
                {
                    "id": "202",
                    "name": "Швабры",
                    "parent_id": "201",
                    "full_path": "Дом и сад > Уборка > Швабры",
                    "level": 2,
                },
                {
                    "id": "203",
                    "name": "Ведра",
                    "parent_id": "201",
                    "full_path": "Дом и сад > Уборка > Ведра",
                    "level": 2,
                },
                {"id": "3", "name": "Одежда", "parent_id": None, "full_path": "Одежда", "level": 0},
                {
                    "id": "301",
                    "name": "Мужская одежда",
                    "parent_id": "3",
                    "full_path": "Одежда > Мужская одежда",
                    "level": 1,
                },
                {
                    "id": "302",
                    "name": "Футболки",
                    "parent_id": "301",
                    "full_path": "Одежда > Мужская одежда > Футболки",
                    "level": 2,
                },
                {
                    "id": "303",
                    "name": "Женская одежда",
                    "parent_id": "3",
                    "full_path": "Одежда > Женская одежда",
                    "level": 1,
                },
                {
                    "id": "4",
                    "name": "Продукты питания",
                    "parent_id": None,
                    "full_path": "Продукты питания",
                    "level": 0,
                },
                {
                    "id": "401",
                    "name": "Чай и кофе",
                    "parent_id": "4",
                    "full_path": "Продукты питания > Чай и кофе",
                    "level": 1,
                },
                {
                    "id": "402",
                    "name": "Чай",
                    "parent_id": "401",
                    "full_path": "Продукты питания > Чай и кофе > Чай",
                    "level": 2,
                },
            ],
            "wildberries": [
                {
                    "id": "100",
                    "name": "Электроника",
                    "parent_id": None,
                    "full_path": "Электроника",
                    "level": 0,
                },
                {
                    "id": "101",
                    "name": "Мобильные телефоны",
                    "parent_id": "100",
                    "full_path": "Электроника > Мобильные телефоны",
                    "level": 1,
                },
                {
                    "id": "102",
                    "name": "Ноутбуки и планшеты",
                    "parent_id": "100",
                    "full_path": "Электроника > Ноутбуки и планшеты",
                    "level": 1,
                },
                {
                    "id": "103",
                    "name": "Аудиотехника",
                    "parent_id": "100",
                    "full_path": "Электроника > Аудиотехника",
                    "level": 1,
                },
                {
                    "id": "1031",
                    "name": "Наушники и гарнитуры",
                    "parent_id": "103",
                    "full_path": "Электроника > Аудиотехника > Наушники и гарнитуры",
                    "level": 2,
                },
                {
                    "id": "200",
                    "name": "Товары для дома",
                    "parent_id": None,
                    "full_path": "Товары для дома",
                    "level": 0,
                },
                {
                    "id": "201",
                    "name": "Уборка и хранение",
                    "parent_id": "200",
                    "full_path": "Товары для дома > Уборка и хранение",
                    "level": 1,
                },
                {
                    "id": "202",
                    "name": "Швабры и ведра",
                    "parent_id": "201",
                    "full_path": "Товары для дома > Уборка и хранение > Швабры и ведра",
                    "level": 2,
                },
                {
                    "id": "300",
                    "name": "Одежда",
                    "parent_id": None,
                    "full_path": "Одежда",
                    "level": 0,
                },
                {
                    "id": "301",
                    "name": "Мужская одежда",
                    "parent_id": "300",
                    "full_path": "Одежда > Мужская одежда",
                    "level": 1,
                },
                {
                    "id": "302",
                    "name": "Футболки и майки",
                    "parent_id": "301",
                    "full_path": "Одежда > Мужская одежда > Футболки и майки",
                    "level": 2,
                },
                {
                    "id": "303",
                    "name": "Женская одежда",
                    "parent_id": "300",
                    "full_path": "Одежда > Женская одежда",
                    "level": 1,
                },
                {
                    "id": "400",
                    "name": "Продукты питания",
                    "parent_id": None,
                    "full_path": "Продукты питания",
                    "level": 0,
                },
                {
                    "id": "401",
                    "name": "Чай",
                    "parent_id": "400",
                    "full_path": "Продукты питания > Чай",
                    "level": 1,
                },
            ],
            "yandex": [
                {
                    "id": "1000",
                    "name": "Электроника",
                    "parent_id": None,
                    "full_path": "Электроника",
                    "level": 0,
                },
                {
                    "id": "1001",
                    "name": "Мобильные телефоны",
                    "parent_id": "1000",
                    "full_path": "Электроника > Мобильные телефоны",
                    "level": 1,
                },
                {
                    "id": "1002",
                    "name": "Ноутбуки",
                    "parent_id": "1000",
                    "full_path": "Электроника > Ноутбуки",
                    "level": 1,
                },
                {
                    "id": "1003",
                    "name": "Аудиотехника",
                    "parent_id": "1000",
                    "full_path": "Электроника > Аудиотехника",
                    "level": 1,
                },
                {
                    "id": "1031",
                    "name": "Наушники",
                    "parent_id": "1003",
                    "full_path": "Электроника > Аудиотехника > Наушники",
                    "level": 2,
                },
                {
                    "id": "2000",
                    "name": "Дом и дача",
                    "parent_id": None,
                    "full_path": "Дом и дача",
                    "level": 0,
                },
                {
                    "id": "2001",
                    "name": "Уборка",
                    "parent_id": "2000",
                    "full_path": "Дом и дача > Уборка",
                    "level": 1,
                },
                {
                    "id": "2002",
                    "name": "Швабры",
                    "parent_id": "2001",
                    "full_path": "Дом и дача > Уборка > Швабры",
                    "level": 2,
                },
                {
                    "id": "3000",
                    "name": "Одежда и обувь",
                    "parent_id": None,
                    "full_path": "Одежда и обувь",
                    "level": 0,
                },
                {
                    "id": "3001",
                    "name": "Мужская одежда",
                    "parent_id": "3000",
                    "full_path": "Одежда и обувь > Мужская одежда",
                    "level": 1,
                },
                {
                    "id": "3002",
                    "name": "Футболки",
                    "parent_id": "3001",
                    "full_path": "Одежда и обувь > Мужская одежда > Футболки",
                    "level": 2,
                },
                {
                    "id": "3003",
                    "name": "Женская одежда",
                    "parent_id": "3000",
                    "full_path": "Одежда и обувь > Женская одежда",
                    "level": 1,
                },
                {
                    "id": "4000",
                    "name": "Продукты питания",
                    "parent_id": None,
                    "full_path": "Продукты питания",
                    "level": 0,
                },
                {
                    "id": "4001",
                    "name": "Чай",
                    "parent_id": "4000",
                    "full_path": "Продукты питания > Чай",
                    "level": 1,
                },
            ],
        }

        return mock_categories.get(platform, [])

    # =====================================================================
    # СОХРАНЕНИЕ В БД
    # =====================================================================

    def _save_categories_to_db(self, platform: str, categories: list[dict]):
        """Сохранить категории в БД (без дубликатов)"""
        db = SessionLocal()
        try:
            saved_count = 0
            for cat in categories:
                existing = (
                    db.query(Category)
                    .filter(Category.platform == platform, Category.category_id == cat["id"])
                    .first()
                )

                if not existing:
                    new_cat = Category(
                        platform=platform,
                        category_id=cat["id"],
                        name=cat["name"],
                        parent_id=cat.get("parent_id"),
                        full_path=cat.get("full_path"),
                        level=cat.get("level", 0),
                    )
                    db.add(new_cat)
                    saved_count += 1

            db.commit()
            if saved_count > 0:
                logger.info(f"Сохранено {saved_count} новых категорий для {platform}")
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка сохранения категорий: {e}")
        finally:
            db.close()

    def get_mapping_for_product(
        self, source_platform: str, category_name: str, target_platform: str, user_id: int
    ) -> dict | None:
        """
        Найти маппинг для товара по имени категории.
        Сначала ищет ID категории по имени, затем ищет маппинг для этого ID.
        """
        if not category_name or category_name == "Не указана":
            return None

        db = SessionLocal()
        try:
            # 1. Находим ID исходной категории по имени и платформе
            source_category = (
                db.query(Category)
                .filter(Category.platform == source_platform, Category.name == category_name)
                .first()
            )

            if not source_category:
                return None

            # 2. Ищем сохраненный маппинг для этого пользователя и категории
            mapping = (
                db.query(CategoryMapping)
                .filter(
                    CategoryMapping.user_id == user_id,
                    CategoryMapping.source_platform == source_platform,
                    CategoryMapping.source_category_id == source_category.category_id,
                    CategoryMapping.target_platform == target_platform,
                )
                .first()
            )

            if mapping:
                # Получаем имя целевой категории для возврата
                target_cat = (
                    db.query(Category)
                    .filter(
                        Category.platform == target_platform,
                        Category.category_id == mapping.target_category_id,
                    )
                    .first()
                )

                return {
                    "target_category_id": mapping.target_category_id,
                    "target_category_name": target_cat.name if target_cat else "Неизвестно",
                    "confidence": mapping.confidence,
                    "is_manual": mapping.is_manual,
                }

            return None
        finally:
            db.close()


# Глобальный экземпляр
category_service = CategoryService()
