"""
Роутер для миграции товаров (одиночной и пакетной).
⚠️ ВАЖНО: /migrate/batch объявлен ПЕРЕД /migrate/{product_id},
иначе FastAPI будет матчить "batch" как {product_id} → 422.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from core.auth import get_current_user
from database.models import User
from database.repository import repo
from tasks import migrate_product_task, migrate_batch_task, get_progress

router = APIRouter(prefix="/api", tags=["Migration"])


# ---------------------------------------------------------------------------
# Схемы
# ---------------------------------------------------------------------------
class MigrateProductRequest(BaseModel):
    platform: str = Field(..., min_length=2, max_length=50)
    edited_data: Optional[dict] = None


class BatchMigrateRequest(BaseModel):
    product_ids: List[int] = Field(..., min_length=1)
    platform: str = Field(..., min_length=2, max_length=50)


# ---------------------------------------------------------------------------
# ⚠️ СНАЧАЛА КОНКРЕТНЫЕ ПУТИ, ПОТОМ С ПАРАМЕТРАМИ
# ---------------------------------------------------------------------------

@router.post("/migrate/batch")
def start_batch_migration(
    request: BatchMigrateRequest,
    current_user: User = Depends(get_current_user),
):
    """Пакетная миграция. ВАЖНО: объявлен ДО /migrate/{product_id}."""
    if not request.product_ids:
        raise HTTPException(status_code=400, detail="Не указаны товары")

    # Проверка принадлежности
    for pid in request.product_ids:
        p = repo.get_by_id(pid, user_id=current_user.id)
        if not p:
            raise HTTPException(
                status_code=404,
                detail=f"Товар #{pid} не найден или не принадлежит вам",
            )

    task = migrate_batch_task.delay(
        product_ids=request.product_ids,
        target_platform=request.platform,
        user_id=current_user.id,
    )

    return {
        "success": True,
        "batch_id": task.id,
        "total": len(request.product_ids),
        "message": f"Пакетная миграция {len(request.product_ids)} товаров запущена",
    }


@router.post("/migrate/{product_id}")
def migrate_product(
    product_id: int,
    request: MigrateProductRequest,
    current_user: User = Depends(get_current_user),
):
    """Одиночная миграция."""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    task = migrate_product_task.delay(
        product_id=product_id,
        target_platform=request.platform,
        user_id=current_user.id,
        edited_data=request.edited_data,
    )

    return {
        "success": True,
        "task_id": task.id,
        "message": f"Миграция товара #{product_id} запущена",
    }


@router.get("/migrate/batch/{batch_id}/progress")
def get_batch_progress(
    batch_id: str,
    current_user: User = Depends(get_current_user),
):
    """Прогресс пакетной миграции."""
    return get_progress(batch_id)