"""Чтение товаров: список с фильтрацией/сортировкой/пагинацией, /stats,
счётчики категорий (О3, один GROUP BY) и подсказки категорий из спеков.

Вынесено без изменений из монолита routers/products.py (Р10).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from database.models import PlatformCategorySpec
from database.models import Product as ProductORM
from database.models import User
from database.repository import repo
from database.session import get_async_db
from models.schemas import Stats
from routers.products._support import SORT_MAP
from services.bulk_ops import escape_like

router = APIRouter()


@router.get("/products/category-counts")
async def products_category_counts(
    status: str = Query(None, description="Фильтр по статусу (all/None — без фильтра)"),
    product_ids: str = Query(None, description="CSV id: считать только по этим товарам"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    ✅ О3: счётчики товаров по категориям назначения одним GROUP BY.
    Замена выгрузки 10 000 товаров в окно экспорта ради «Недостающих шаблонов»:
    один агрегатный SQL вместо полной выборки с атрибутами и вариациями.
    """
    # coalesce+nullif повторяет семантику JS `mapped_category || category || 'Без категории'`:
    # пустая строка считается отсутствием значения, как на фронте
    category_expr = func.coalesce(
        func.nullif(ProductORM.mapped_category, ""),
        func.nullif(ProductORM.category, ""),
        "Без категории",
    )
    stmt = (
        select(category_expr, func.count(ProductORM.id))
        .where(ProductORM.user_id == current_user.id)
        .group_by(category_expr)
    )
    if status and status not in ("all", ""):
        stmt = stmt.where(ProductORM.status == status)
    if product_ids:
        id_list = [int(x) for x in product_ids.split(",") if x.strip().isdigit()]
        if id_list:
            stmt = stmt.where(ProductORM.id.in_(id_list))

    rows = (await db.execute(stmt)).all()
    return {"counts": dict(rows)}


@router.get("/products/categories-suggest")
async def categories_suggest(
    q: str = Query("", max_length=200),
    limit: int = Query(15, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Подсказки категорий назначения из спеков площадок (для автокомплита
    в массовом обновлении). Ищем по частичному совпадению имени.
    """
    pattern = f"%{escape_like(q.strip())}%"
    stmt = (
        select(
            PlatformCategorySpec.category_name,
            func.array_agg(func.distinct(PlatformCategorySpec.platform)),
        )
        .where(PlatformCategorySpec.category_name.ilike(pattern))
        .group_by(PlatformCategorySpec.category_name)
        .order_by(func.length(PlatformCategorySpec.category_name))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return {
        "suggestions": [
            {"name": name, "platforms": sorted(platforms or [])} for name, platforms in rows
        ]
    }


@router.get("/products")
async def get_products(
    search: str | None = Query(None, description="Поиск по названию, SKU, артикулу"),
    status: str | None = Query(
        None, description="Статус: pending | processing | success | error | all"
    ),
    source: str | None = Query(None, description="Источник импорта | all"),
    sort: str = Query(
        "newest",
        description="Сортировка: newest | oldest | name_asc | name_desc | price_asc | price_desc",
    ),
    skip: int = Query(0, ge=0, description="Смещение для пагинации"),
    limit: int = Query(50, ge=1, le=10000, description="Количество товаров на странице"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Получить товары с фильтрацией, сортировкой и пагинацией (неблокирующий AsyncSession).

    Контракт с фронтендом:
      - `status=all` и `source=all` означают "без фильтра"
      - `sort` принимает значения из SORT_MAP
      - `limit` ограничен 10000 сверху (для UI-селекта 25/50/100/200 и экспорта)
    """
    is_admin = current_user.role == "admin"

    norm_status = None if (status in (None, "all", "")) else status
    norm_source = None if (source in (None, "all", "")) else source
    sort_by, sort_order = SORT_MAP.get(sort, SORT_MAP["newest"])
    norm_search = search.strip() if search and search.strip() else None

    return await repo.get_all_async(
        db=db,
        user_id=current_user.id,
        is_admin=is_admin,
        search=norm_search,
        status=norm_status,
        source=norm_source,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=limit,
    )


@router.get("/stats", response_model=Stats)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Получить статистику по товарам текущего пользователя (или все для админа)."""
    is_admin = current_user.role == "admin"
    return await repo.get_stats_async(db=db, user_id=current_user.id, is_admin=is_admin)
