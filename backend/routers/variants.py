"""
Роутер для управления вариациями товаров (SKU по размерам/цветам).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from database.repository import variant_repo, repo
from database.models import User
from core.auth import get_current_user

router = APIRouter(prefix="/api/products", tags=["Variants"])


class VariantInput(BaseModel):
    sku: str
    size: Optional[str] = None
    color: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    external_id: Optional[str] = None
    sort_order: int = 0


@router.get("/{product_id}/variants")
def get_variants(product_id: int, current_user: User = Depends(get_current_user)):
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return {"success": True, "variants": variant_repo.get_by_product(product_id)}


@router.put("/{product_id}/variants")
def set_variants(
    product_id: int,
    variants: List[VariantInput],
    current_user: User = Depends(get_current_user),
):
    """Полностью заменить набор вариаций товара"""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    result = variant_repo.set_variants(product_id, [v.model_dump() for v in variants])
    return {"success": True, "variants": result, "count": len(result)}


@router.delete("/variants/{variant_id}")
def delete_variant(variant_id: int, current_user: User = Depends(get_current_user)):
    success = variant_repo.delete_variant(variant_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Вариация не найдена")
    return {"success": True}