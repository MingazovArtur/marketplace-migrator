"""
Роутер для работы с товарами
"""
from fastapi import APIRouter, HTTPException, Depends
from database.repository import repo
from models.schemas import Stats
from core.auth import get_current_user
from database.models import User

router = APIRouter(prefix="/api", tags=["Products"])


@router.get("/products")
def get_products(current_user: User = Depends(get_current_user)):
    """Получить все товары текущего пользователя"""
    products = repo.get_all(user_id=current_user.id)
    return {"total": len(products), "products": products}


@router.get("/stats", response_model=Stats)
def get_stats(current_user: User = Depends(get_current_user)):
    """Получить статистику по товарам текущего пользователя"""
    return repo.get_stats(user_id=current_user.id)


@router.delete("/products/{product_id}")
def delete_product(
    product_id: int, 
    current_user: User = Depends(get_current_user)
):
    """Удалить товар (только если он принадлежит текущему пользователю)"""
    if repo.delete(product_id, user_id=current_user.id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")