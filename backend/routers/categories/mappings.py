"""
Маппинг категорий между площадками: список, сохранение, удаление.

Вынесено без изменений из монолита routers/categories.py (Р7).
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from core.auth import get_current_user
from database.models import CategoryMapping, User
from database.session import SessionLocal
from routers.categories._support import SaveMappingPayload
from services.category_service import category_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/category-mapping")
def get_category_mappings(
    source_platform: str = None,
    target_platform: str = None,
    current_user: User = Depends(get_current_user),
):
    """Список сохранённых маппингов категорий текущего пользователя."""
    db = SessionLocal()
    try:
        q = db.query(CategoryMapping).filter(CategoryMapping.user_id == current_user.id)
        if source_platform:
            q = q.filter(CategoryMapping.source_platform == source_platform)
        if target_platform:
            q = q.filter(CategoryMapping.target_platform == target_platform)
        rows = q.order_by(CategoryMapping.id).all()
        return {
            "success": True,
            "mappings": [
                {
                    "id": r.id,
                    "source_platform": r.source_platform,
                    "source_category_id": r.source_category_id,
                    "target_platform": r.target_platform,
                    "target_category_id": r.target_category_id,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


@router.post("/category-mapping")
def save_category_mapping(
    source_platform: str | None = Query(default=None),
    source_category_id: str | None = Query(default=None),
    target_platform: str | None = Query(default=None),
    target_category_id: str | None = Query(default=None),
    payload: SaveMappingPayload | None = Body(default=None),
    current_user: User = Depends(get_current_user),
):
    """Сохранить маппинг категории для текущего пользователя (поддерживает query и body)."""
    sp = source_platform or (payload.source_platform if payload else None)
    sc = source_category_id or (payload.source_category_id if payload else None)
    tp = target_platform or (payload.target_platform if payload else None)
    tc = target_category_id or (payload.target_category_id if payload else None)

    if not all([sp, sc, tp, tc]):
        raise HTTPException(status_code=400, detail="Укажите все поля маппинга категорий")

    result = category_service.save_category_mapping(
        current_user.id,
        sp,
        str(sc),
        tp,
        str(tc),
    )

    if result["success"]:
        return result

    raise HTTPException(status_code=500, detail=result["error"])


@router.delete("/category-mapping/{mapping_id}")
def delete_category_mapping(
    mapping_id: int,
    current_user: User = Depends(get_current_user),
):
    """Удаление маппинга. Только владелец может удалить свою запись."""
    db = SessionLocal()
    try:
        row = (
            db.query(CategoryMapping)
            .filter(
                CategoryMapping.id == mapping_id,
                CategoryMapping.user_id == current_user.id,
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Маппинг не найден")

        db.delete(row)
        db.commit()
        return {"success": True}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка удаления маппинга") from None
    finally:
        db.close()
