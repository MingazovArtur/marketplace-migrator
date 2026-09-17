"""
Роутер для управления характеристиками товаров.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from database.repository import attr_repo, repo
from database.models import User
from core.auth import get_current_user

router = APIRouter(prefix="/api/products", tags=["Attributes"])


class AttributeCreate(BaseModel):
    name: str
    value: str
    platform_attribute_id: Optional[str] = None


class AttributeUpdate(BaseModel):
    name: str
    value: str
    platform_attribute_id: Optional[str] = None


class BulkAttributesUpdate(BaseModel):
    """Массовое обновление характеристик для группы товаров"""
    product_ids: List[int]
    attributes: List[AttributeUpdate]  # набор характеристик для всех товаров


@router.get("/{product_id}/attributes")
def get_attributes(product_id: int, current_user: User = Depends(get_current_user)):
    """Получить характеристики товара"""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return {"success": True, "attributes": attr_repo.get_by_product(product_id)}


@router.put("/{product_id}/attributes")
def set_attributes(
    product_id: int,
    attributes: List[AttributeUpdate],
    current_user: User = Depends(get_current_user),
):
    """Заменить все характеристики товара на новые"""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    attrs_dict = [a.model_dump() for a in attributes]
    result = attr_repo.set_attributes(product_id, attrs_dict)
    return {"success": True, "attributes": result, "count": len(result)}


@router.post("/{product_id}/attributes")
def add_attribute(
    product_id: int,
    attribute: AttributeCreate,
    current_user: User = Depends(get_current_user),
):
    """Добавить одну характеристику к товару"""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    result = attr_repo.add_attribute(
        product_id=product_id,
        name=attribute.name,
        value=attribute.value,
        platform_attribute_id=attribute.platform_attribute_id,
    )
    return {"success": True, "attribute": result}


@router.delete("/attributes/{attribute_id}")
def delete_attribute(
    attribute_id: int,
    current_user: User = Depends(get_current_user),
):
    """Удалить характеристику"""
    success = attr_repo.delete_attribute(attribute_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Характеристика не найдена")
    return {"success": True}


@router.put("/attributes/bulk")
def bulk_set_attributes(
    payload: BulkAttributesUpdate,
    current_user: User = Depends(get_current_user),
):
    """Массовая установка характеристик для нескольких товаров"""
    if not payload.product_ids:
        raise HTTPException(status_code=400, detail="Не указаны товары")

    attrs_dict = [a.model_dump() for a in payload.attributes]
    updated = 0
    for pid in payload.product_ids:
        product = repo.get_by_id(pid, user_id=current_user.id)
        if not product:
            continue
        attr_repo.set_attributes(pid, attrs_dict)
        updated += 1

    return {"success": True, "updated": updated}