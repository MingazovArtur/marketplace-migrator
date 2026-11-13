"""Общие схемы и хелперы роутера товаров.

Вынесено без изменений из монолита routers/products.py (Р10):
карта сортировок, схемы запросов (bulk-delete/delete-all/правка/undo)
и проверка категории назначения по спекам площадок.
"""

import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PlatformCategorySpec

logger = logging.getLogger(__name__)


# Карта сортировок фронтенда -> (поле, направление) для репозитория
SORT_MAP = {
    "newest": ("created_at", "desc"),
    "oldest": ("created_at", "asc"),
    "name_asc": ("name", "asc"),
    "name_desc": ("name", "desc"),
    "price_asc": ("price", "asc"),
    "price_desc": ("price", "desc"),
}

# Сколько undo-снапшотов храним на пользователя (ротация в services/edit_history.py)
SNAPSHOTS_PER_USER = 20


# ==================== Схемы запросов удаления ====================


class BulkDeleteRequest(BaseModel):
    product_ids: list[int]


class DeleteAllRequest(BaseModel):
    confirm: bool = False


class ProductUpdateRequest(BaseModel):
    """Точечное обновление товара — кнопка «Сохранить» в окне миграции."""

    name: str | None = None
    price: float | None = None
    # Категория назначения (как в bulk-update пишется в mapped_category)
    category: str | None = None


class UndoRequest(BaseModel):
    """Отмена операции правки: по id или последняя неотменённая."""

    snapshot_id: int | None = None


# ==================== Хелпер: валидация категории по спекам ====================


async def _validate_category_against_specs_async(db: AsyncSession, category_name: str) -> dict:
    """
    Неблокирующая проверка: существует ли ТОЧНОЕ имя категории в platform_category_specs
    хотя бы для одной из площадок.

    Возвращает:
        {"exists": True, "platforms": ["ozon", "wb"]} — если есть в спеках
        {"exists": False, "platforms": []} — если не нашлась ни в одной площадке
    """
    if not category_name:
        return {"exists": False, "platforms": []}

    try:
        stmt = (
            select(PlatformCategorySpec.platform)
            .where(PlatformCategorySpec.category_name == category_name.strip())
            .distinct()
        )
        res = await db.execute(stmt)
        platforms = [r[0] for r in res.all()]
        return {"exists": len(platforms) > 0, "platforms": platforms}
    except Exception as e:
        logger.warning(f"Не удалось проверить категорию '{category_name}' по спекам: {e}")
        return {"exists": True, "platforms": ["?"]}  # при ошибке не блокируем
