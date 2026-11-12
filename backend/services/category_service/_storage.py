"""Операции хранения категорий и маппингов (SQLAlchemy, SessionLocal).

Чистые функции: каждая открывает/закрывает свою сессию.
Вынесено без изменений из монолита services/category_service.py (Р6).
"""

import logging

from database.models import Category, CategoryMapping
from database.session import SessionLocal

logger = logging.getLogger(__name__)


def load_categories_from_db(platform: str) -> list[dict]:
    """Активные категории площадки из БД (пустой список — если ничего нет)."""
    db = SessionLocal()
    try:
        categories = (
            db.query(Category)
            .filter(Category.platform == platform, Category.is_active == True)
            .all()
        )
        return [
            {
                "id": c.category_id,
                "name": c.name,
                "parent_id": c.parent_id,
                "full_path": c.full_path,
                "level": c.level,
            }
            for c in categories
        ]
    finally:
        db.close()


def save_categories_to_db(platform: str, categories: list[dict]) -> None:
    """Сохранить категории в БД (без дубликатов)."""
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


def find_category_mapping(
    source_platform: str,
    source_category_id: str,
    target_platform: str,
    user_id: int | None = None,
) -> dict | None:
    """Найти сохраненный маппинг категории."""
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


def upsert_category_mapping(
    user_id: int,
    source_platform: str,
    source_category_id: str,
    target_platform: str,
    target_category_id: str,
    is_manual: bool = True,
) -> dict:
    """Сохранить (создать или обновить) маппинг категории."""
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


def find_mapping_for_product(
    source_platform: str, category_name: str, target_platform: str, user_id: int
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
