"""
Роутер для миграции товаров (одиночной и пакетной).

⚠️ ВАЖНО: /migrate/batch объявлен ПЕРЕД /migrate/{product_id},
иначе FastAPI будет матчить "batch" как {product_id} → 422.

Rate-limits (на идентификатор: user_id или IP):
  - /migrate/batch                : 5/min, 50/day   (Celery-задачи, самые тяжёлые)
  - /migrate/{product_id}         : 20/min          (одиночная миграция)
  - /migrate/batch/{id}/progress  : 60/min          (polling прогресса)
"""


from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.rate_limit import limiter
from database.models import User
from database.repository import repo
from tasks import get_progress, migrate_batch_task, migrate_product_task

router = APIRouter(prefix="/api", tags=["Migration"])


# ---------------------------------------------------------------------------
# Схемы
# ---------------------------------------------------------------------------
class MigrateProductRequest(BaseModel):
    platform: str = Field(..., min_length=2, max_length=50)
    edited_data: dict | None = None


class BatchMigrateRequest(BaseModel):
    product_ids: list[int] = Field(..., min_length=1)
    platform: str = Field(..., min_length=2, max_length=50)


# ---------------------------------------------------------------------------
# ⚠️ СНАЧАЛА КОНКРЕТНЫЕ ПУТИ, ПОТОМ С ПАРАМЕТРАМИ
# ---------------------------------------------------------------------------


# ==================== ПАКЕТНАЯ МИГРАЦИЯ (самый строгий лимит) ====================
@limiter.limit("5/minute;50/day")
@router.post("/migrate/batch")
def start_batch_migration(
    request: Request,  # ← добавлен для slowapi
    payload: BatchMigrateRequest,  # ← переименован (был request)
    current_user: User = Depends(get_current_user),
):
    """Пакетная миграция. ВАЖНО: объявлен ДО /migrate/{product_id}."""
    if not payload.product_ids:  # ← использование нового имени
        raise HTTPException(status_code=400, detail="Не указаны товары")

    # Проверка принадлежности
    for pid in payload.product_ids:  # ← использование нового имени
        p = repo.get_by_id(pid, user_id=current_user.id)
        if not p:
            raise HTTPException(
                status_code=404,
                detail=f"Товар #{pid} не найден или не принадлежит вам",
            )

    task = migrate_batch_task.delay(
        product_ids=payload.product_ids,  # ← использование нового имени
        target_platform=payload.platform,  # ← использование нового имени
        user_id=current_user.id,
    )

    return {
        "success": True,
        "batch_id": task.id,
        "total": len(payload.product_ids),  # ← использование нового имени
        "message": f"Пакетная миграция {len(payload.product_ids)} товаров запущена",
    }


# ==================== ОДИНОЧНАЯ МИГРАЦИЯ ====================
@limiter.limit("20/minute")
@router.post("/migrate/{product_id}")
def migrate_product(
    request: Request,  # ← добавлен для slowapi
    product_id: int,
    payload: MigrateProductRequest,  # ← переименован (был request)
    current_user: User = Depends(get_current_user),
):
    """Одиночная миграция."""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    task = migrate_product_task.delay(
        product_id=product_id,
        target_platform=payload.platform,  # ← использование нового имени
        user_id=current_user.id,
        edited_data=payload.edited_data,  # ← использование нового имени
    )

    return {
        "success": True,
        "task_id": task.id,
        "message": f"Миграция товара #{product_id} запущена",
    }


# ==================== ПРОГРЕСС ПАКЕТНОЙ МИГРАЦИИ (polling) ====================
@limiter.limit("60/minute")
@router.get("/migrate/batch/{batch_id}/progress")
def get_batch_progress(
    request: Request,  # ← добавлен для slowapi
    batch_id: str,
    current_user: User = Depends(get_current_user),
):
    """Прогресс пакетной миграции."""
    return get_progress(batch_id)
