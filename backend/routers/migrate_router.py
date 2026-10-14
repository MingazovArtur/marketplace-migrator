"""
Роутер для миграции товаров (предпросмотр, одиночная и пакетная миграция).

⚠️ ВАЖНО: /migrate/preview и /migrate/batch объявлены ПЕРЕД /migrate/{product_id},
иначе FastAPI будет матчить "preview" или "batch" как {product_id} → 422.

Rate-limits (на идентификатор: user_id или IP):
  - /migrate/preview              : 30/min          (предпросмотр миграции)
  - /migrate/batch                : 5/min, 50/day   (Celery-задачи, самые тяжёлые)
  - /migrate/{product_id}         : 20/min          (одиночная миграция)
  - /migrate/batch/{id}/progress  : 60/min          (polling прогресса)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.platforms import PRICE_RULES, Platform
from core.rate_limit import limiter
from database.models import User
from database.repository import repo
from services.category_mapper import CategoryMapper
from services.category_service import category_service
from services.platform_utils import detect_platform
from tasks import get_progress, migrate_batch_task, migrate_product_task

router = APIRouter(prefix="/api", tags=["Migration"])
category_mapper = CategoryMapper()


# ---------------------------------------------------------------------------
# Схемы
# ---------------------------------------------------------------------------
class MigratePreviewRequest(BaseModel):
    product_id: int
    target_marketplace: str = Field(default="", max_length=50)
    platform: str = Field(default="", max_length=50)

    def get_target(self) -> str:
        return (self.target_marketplace or self.platform).strip().lower()


class MigrateProductRequest(BaseModel):
    platform: str = Field(..., min_length=2, max_length=50)
    edited_data: dict | None = None


class BatchMigrateRequest(BaseModel):
    product_ids: list[int] = Field(..., min_length=1)
    platform: str = Field(..., min_length=2, max_length=50)


# ---------------------------------------------------------------------------
# ⚠️ СНАЧАЛА КОНКРЕТНЫЕ ПУТИ, ПОТОМ С ПАРАМЕТРАМИ
# ---------------------------------------------------------------------------


# ==================== ПРЕДПРОСМОТР МИГРАЦИИ ====================
@limiter.limit("30/minute")
@router.post("/migrate/preview")
def preview_migration(
    request: Request,
    payload: MigratePreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """Предпросмотр миграции товара (категория и пересчёт цены)."""
    product = repo.get_by_id(payload.product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    target = payload.get_target()
    if target not in Platform.all_values():
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {target}")

    source_platform = detect_platform(product.get("source", ""))
    mapping = category_service.get_mapping_for_product(
        source_platform, product.get("category"), target, current_user.id
    )

    if mapping and mapping.get("is_manual"):
        target_category_name = mapping["target_category_name"]
        reason = "Использован ваш ручной маппинг"
    elif product.get("mapped_category"):
        target_category_name = product.get("mapped_category")
        reason = "Использована ранее выбранная категория назначения"
    else:
        auto_map = category_mapper.auto_map_by_text(product.get("category") or "Дом и сад", target)
        target_category_name = auto_map["name"]
        reason = f"Автоопределение по ключевым словам в категории '{product.get('category')}'"

    price_multiplier = float(PRICE_RULES.get(target, 1.0))
    new_price = round(float(product.get("price") or 0) * price_multiplier, 2)

    return {
        "success": True,
        "preview": {
            "original": {
                "name": product.get("name"),
                "price": product.get("price"),
                "category": product.get("category") or "Не указана",
            },
            "target": {
                "name": product.get("name"),
                "price": new_price,
                "category": target_category_name,
                "category_id": mapping["target_category_id"] if mapping else None,
            },
            "mapping_reason": reason,
        },
    }


# ==================== ПАКЕТНАЯ МИГРАЦИЯ (самый строгий лимит) ====================
@limiter.limit("5/minute;50/day")
@router.post("/migrate/batch")
def start_batch_migration(
    request: Request,
    payload: BatchMigrateRequest,
    current_user: User = Depends(get_current_user),
):
    """Пакетная миграция. ВАЖНО: объявлен ДО /migrate/{product_id}."""
    if not payload.product_ids:
        raise HTTPException(status_code=400, detail="Не указаны товары")

    target = payload.platform.strip().lower()
    if target not in Platform.all_values():
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {target}")

    available_ids = []
    for pid in payload.product_ids:
        p = repo.get_by_id(pid, user_id=current_user.id)
        if not p:
            raise HTTPException(
                status_code=404,
                detail=f"Товар #{pid} не найден или не принадлежит вам",
            )
        if p.get("status") != "processing":
            available_ids.append(pid)

    if not available_ids:
        raise HTTPException(
            status_code=400,
            detail="Все выбранные товары уже находятся в процессе переноса",
        )

    task = migrate_batch_task.delay(
        product_ids=available_ids,
        target_platform=target,
        user_id=current_user.id,
    )

    return {
        "success": True,
        "batch_id": task.id,
        "task_id": task.id,
        "total": len(available_ids),
        "message": f"Пакетная миграция {len(available_ids)} товаров запущена",
    }


# ==================== ОДИНОЧНАЯ МИГРАЦИЯ ====================
@limiter.limit("20/minute")
@router.post("/migrate/{product_id}")
def migrate_product(
    request: Request,
    product_id: int,
    payload: MigrateProductRequest,
    current_user: User = Depends(get_current_user),
):
    """Одиночная миграция."""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    if product.get("status") == "processing":
        raise HTTPException(
            status_code=400,
            detail="Товар уже находится в процессе переноса. Дождитесь завершения.",
        )

    target = payload.platform.strip().lower()
    if target not in Platform.all_values():
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {target}")

    task = migrate_product_task.delay(
        product_id=product_id,
        target_platform=target,
        user_id=current_user.id,
        edited_data=payload.edited_data,
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
    request: Request,
    batch_id: str,
    current_user: User = Depends(get_current_user),
):
    """Прогресс миграции (единый для одиночной и пакетной)."""
    return get_progress(batch_id)