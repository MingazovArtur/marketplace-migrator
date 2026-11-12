"""
Спецификации категорий площадки: чтение и удаление (CRUD).

ВАЖНО: порядок маршрутов внутри модуля имеет значение.
/api/specs/{platform}/names ОБЯЗАН быть объявлен ДО
/api/specs/{platform}/{category_id:path} — иначе «names» ловится как
category_id (то же про /key-source и /refresh/... — они в specs_refresh.py,
который подключается до этого модуля).

Вынесено без изменений из монолита routers/categories.py (Р7).
"""

import logging
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_

from core.auth import get_current_user
from database.models import PlatformCategorySpec, User
from database.session import SessionLocal
from models.schemas import PlatformCategorySpecResponse
from routers.categories._support import _require_admin
from services import cache_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/specs/{platform}/names")
def list_spec_names(platform: str, current_user: User = Depends(get_current_user)):
    """
    ЛЁГКИЙ список имён категорий спеков (для datalist/автокомплита).
    КЭШИРУЕТСЯ на 1 час для снижения нагрузки на БД.
    """
    cache_key = f"specs:{platform}:names"

    cached = cache_service.get(cache_key)
    if cached is not None:
        return cached

    db = SessionLocal()
    try:
        rows = (
            db.query(PlatformCategorySpec.category_name)
            .filter(PlatformCategorySpec.platform == platform)
            .order_by(PlatformCategorySpec.category_name)
            .all()
        )
        names = [r[0] for r in rows if r[0]]
        result = {
            "platform": platform,
            "count": len(names),
            "names": names,
        }

        cache_service.set(cache_key, result, ttl=3600)

        logger.info(
            f"📋 /specs/{platform}/names: {len(names)} категорий (загружено из БД и закэшировано)"
        )
        return result
    finally:
        db.close()


@router.get("/specs/{platform}")
def list_specs(platform: str, current_user: User = Depends(get_current_user)):
    """Полный список спеков всех категорий площадки (с атрибутами, словарями)."""
    db = SessionLocal()
    try:
        rows = (
            db.query(PlatformCategorySpec)
            .filter(PlatformCategorySpec.platform == platform)
            .order_by(PlatformCategorySpec.category_name)
            .all()
        )
        return {
            "platform": platform,
            "count": len(rows),
            "specs": [PlatformCategorySpecResponse.model_validate(r) for r in rows],
        }
    finally:
        db.close()


@router.delete("/specs/{platform}")
def delete_all_platform_specs(
    platform: str,
    current_user: User = Depends(get_current_user),
):
    """Удалить ВСЕ спецификации указанной площадки (только для администратора)."""
    _require_admin(current_user)
    db = SessionLocal()
    try:
        deleted = (
            db.query(PlatformCategorySpec)
            .filter(PlatformCategorySpec.platform == platform)
            .delete(synchronize_session=False)
        )
        db.commit()
        cache_service.delete_pattern(f"specs:{platform}:*")
        logger.warning(
            f"🗑 ADMIN DELETE ALL SPECS: user={current_user.id} platform={platform} deleted={deleted}"
        )
        return {
            "success": True,
            "platform": platform,
            "deleted": deleted,
            "message": f"Удалено спецификаций ({platform}): {deleted}",
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка удаления всех спеков {platform}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления спеков: {e}")
    finally:
        db.close()


@router.delete("/specs/{platform}/{category_id:path}")
def delete_single_spec(
    platform: str,
    category_id: str,
    current_user: User = Depends(get_current_user),
):
    """Удалить спецификацию одной категории по её ID или имени (только для администратора)."""
    _require_admin(current_user)
    decoded_id = unquote(category_id).strip()
    db = SessionLocal()
    try:
        row = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == platform,
                or_(
                    PlatformCategorySpec.category_id == decoded_id,
                    PlatformCategorySpec.category_name == decoded_id,
                ),
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Спецификация «{decoded_id}» не найдена")

        cat_name = row.category_name
        db.delete(row)
        db.commit()
        cache_service.delete_pattern(f"specs:{platform}:*")
        logger.info(
            f"🗑 ADMIN DELETE SPEC: user={current_user.id} platform={platform} category='{cat_name}'"
        )
        return {
            "success": True,
            "platform": platform,
            "category_name": cat_name,
            "message": f"Спецификация «{cat_name}» удалена",
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка удаления спека {platform}/{decoded_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления спека: {e}")
    finally:
        db.close()


@router.get("/specs/{platform}/{category_id:path}")
def get_spec(
    platform: str,
    category_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Спек одной категории по её category_id ИЛИ category_name.
    Использует :path, чтобы корректно обрабатывать названия со слэшами
    (например, «3D-печать и сканирование / 3D-принтер»).
    """
    decoded_id = unquote(category_id).strip()
    db = SessionLocal()
    try:
        row = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == platform,
                or_(
                    PlatformCategorySpec.category_id == decoded_id,
                    PlatformCategorySpec.category_name == decoded_id,
                ),
            )
            .first()
        )
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Спека «{decoded_id}» не найдена. Сначала обновите через «Загрузить спеки»",
            )
        return PlatformCategorySpecResponse.model_validate(row)
    finally:
        db.close()
