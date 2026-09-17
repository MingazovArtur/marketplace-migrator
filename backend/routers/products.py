"""
Роутер для работы с товарами.
Поддерживает фильтрацию, сортировку и пагинацию.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from database.repository import repo
from models.schemas import Stats
from core.auth import get_current_user
from database.models import User
from typing import Optional
from models.schemas import Stats, ProductBulkUpdate


router = APIRouter(prefix="/api", tags=["Products"])

@router.put("/products/bulk-update")
def bulk_update_products(
    request: ProductBulkUpdate,
    current_user: User = Depends(get_current_user),
):
    """Массовое обновление цены/бренда/категории для выбранных товаров."""
    if not request.product_ids:
        raise HTTPException(status_code=400, detail="Не указаны товары")
    if all(v is None for v in (request.price, request.price_percent, request.brand, request.category)):
        raise HTTPException(status_code=400, detail="Не указаны поля для обновления")

    updated = 0
    for pid in request.product_ids:
        p = repo.get_by_id(pid, user_id=current_user.id)
        if not p:
            continue
        upd = {}
        if request.price_percent is not None:
            upd["price"] = round((p["price"] or 0) * (1 + request.price_percent / 100), 2)
        elif request.price is not None:
            upd["price"] = request.price
        if request.brand is not None:
            upd["brand"] = request.brand
        if request.category is not None:
            upd["category"] = request.category
        if upd:
            repo.update(pid, upd, user_id=current_user.id)
            updated += 1

    return {"success": True, "updated": updated}

@router.get("/products")
def get_products(
    search: Optional[str] = Query(None, description="Поиск по названию"),
    status: Optional[str] = Query(None, description="Фильтр по статусу (pending, success, error, processing)"),
    source: Optional[str] = Query(None, description="Фильтр по источнику (ozon, wildberries, yandex)"),
    sort_by: str = Query("created_at", description="Поле сортировки (created_at, price, name, status)"),
    sort_order: str = Query("desc", description="Направление сортировки (asc, desc)"),
    skip: int = Query(0, ge=0, description="Смещение для пагинации"),
    limit: int = Query(50, ge=1, le=100, description="Количество товаров на странице"),
    current_user: User = Depends(get_current_user)
):
    """Получить товары с фильтрацией, сортировкой и пагинацией"""
    is_admin = current_user.role == "admin"
    result = repo.get_all(
        user_id=current_user.id,
        is_admin=is_admin,
        search=search,
        status=status,
        source=source,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=limit
    )
    return result


@router.get("/stats", response_model=Stats)
def get_stats(current_user: User = Depends(get_current_user)):
    """Получить статистику по товарам текущего пользователя (или все для админа)"""
    is_admin = current_user.role == "admin"
    return repo.get_stats(user_id=current_user.id, is_admin=is_admin)


@router.delete("/products/{product_id}")
def delete_product(
    product_id: int, 
    current_user: User = Depends(get_current_user)
):
    """Удалить товар (только если он принадлежит текущему пользователю)"""
    user_id = None if current_user.role == "admin" else current_user.id
    
    if repo.delete(product_id, user_id=user_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")