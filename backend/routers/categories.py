"""
Роутер для работы со справочниками категорий и маппингом
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
import httpx
from core.config import settings
from services.yandex_specs import refresh_yandex_specs
from services.wb_specs import refresh_wildberries_specs
from services.category_service import category_service
from core.auth import get_current_user
from database.models import CategoryMapping, User, PlatformCategorySpec
from database.session import SessionLocal
from services.ozon_specs import refresh_ozon_specs
from models.schemas import (
    RefreshSpecRequest,
    CategorySpecListResponse,
    PlatformCategorySpecResponse,
)
from tasks import refresh_specs_task, get_progress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Categories"])

# ========== Спецификации категорий площадок ==========


@router.post("/specs/{platform}/refresh")
async def refresh_specs(
    platform: str,
    payload: RefreshSpecRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Обновить спецификации категорий площадки через её API.

    ✅ Ozon — запускается ФОНОВО через Celery (8000+ категорий),
       возвращает task_id для polling прогресса через
       GET /specs/{platform}/refresh/{task_id}/progress.

    ✅ Yandex / WB — пока синхронно (они быстрее).
    """
    if platform not in ("ozon", "yandex", "wildberries"):
        raise HTTPException(status_code=501, detail=f"Загрузчик для {platform} ещё не реализован")

    raw_key = payload.api_key
    # Fallback: серверный ключ из .env, если пользователь не ввёл свой
    if not raw_key and platform == "ozon" and settings.OZON_CLIENT_ID and settings.OZON_API_KEY:
        raw_key = f"{settings.OZON_CLIENT_ID}:{settings.OZON_API_KEY}"

    if not raw_key:
        raise HTTPException(status_code=400, detail="Не указан API-ключ площадки")

    try:
        # ==================== OZON — фоновая загрузка ====================
        if platform == "ozon":
            task = refresh_specs_task.delay(
                user_id=current_user.id,
                platform=platform,
                raw_api_key=raw_key,
                category_ids=payload.category_ids,
            )
            logger.info(
                f"Ozon specs refresh queued: task_id={task.id}, user={current_user.id}"
            )
            return {
                "success": True,
                "task_id": task.id,
                "message": "Загрузка спеков Ozon запущена в фоне (8000+ категорий, 20-40 мин)",
            }

        # ==================== WILDBERRIES — синхронно ====================
        if platform == "wildberries":
            result = await refresh_wildberries_specs(
                user_id=current_user.id,
                token=raw_key,
                category_ids=payload.category_ids,
            )
            return {"success": True, **result}

        # ==================== YANDEX — синхронно ====================
        if not payload.business_id:
            raise HTTPException(
                status_code=400,
                detail="Для Яндекс Маркета укажите OAuth-токен и номер кабинета (business_id)",
            )
        result = await refresh_yandex_specs(
            user_id=current_user.id,
            token=raw_key,
            business_id=payload.business_id,
            category_ids=payload.category_ids,
        )
        return {"success": True, **result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка API площадки: {e.response.status_code} — {e.response.text[:200]}",
        )


@router.get("/specs/{platform}/refresh/{task_id}/progress")
def refresh_specs_progress(
    platform: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Прогресс фоновой загрузки спеков.

    ✅ Использует тот же get_progress, что и миграции — единый формат
    ответа (status/done/success/errors/percent) для фронта.
    """
    return get_progress(task_id)


@router.get("/specs/{platform}/key-source")
def spec_key_source(platform: str, current_user: User = Depends(get_current_user)):
    """
    Индикатор: есть ли серверный ключ площадки в .env.
    ✅ Устойчив к ошибкам: при любой проблеме возвращает has_server_key=False.
    """
    has_server_key = False
    try:
        if platform == "ozon":
            client_id = getattr(settings, "OZON_CLIENT_ID", "") or ""
            api_key = getattr(settings, "OZON_API_KEY", "") or ""
            has_server_key = bool(client_id.strip() and api_key.strip())
        # Yandex/WB можно добавить аналогично при необходимости
    except Exception as e:
        logger.warning(f"key-source check failed for {platform}: {e}")
        has_server_key = False

    return {"platform": platform, "has_server_key": has_server_key}


@router.get("/specs/{platform}")
def list_specs(platform: str, current_user: User = Depends(get_current_user)):
    """Список спеков всех категорий площадки для текущего пользователя."""
    db = SessionLocal()
    try:
        rows = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.user_id == current_user.id,
                PlatformCategorySpec.platform == platform,
            )
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


@router.get("/specs/{platform}/{category_id}")
def get_spec(platform: str, category_id: str, current_user: User = Depends(get_current_user)):
    """Спек одной категории."""
    db = SessionLocal()
    try:
        row = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.user_id == current_user.id,
                PlatformCategorySpec.platform == platform,
                PlatformCategorySpec.category_id == category_id,
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Спека не найдена. Сначала обновите через /refresh")
        return PlatformCategorySpecResponse.model_validate(row)
    finally:
        db.close()


# ========== Справочники категорий ==========


@router.get("/categories/{platform}")
def get_categories(platform: str, force_refresh: bool = False):
    """Получить список категорий для платформы"""
    categories = category_service.get_categories(platform, force_refresh)
    return {"success": True, "categories": categories, "total": len(categories)}


@router.get("/categories/{platform}/tree")
def get_categories_tree(platform: str):
    """Получить категории в виде дерева"""
    categories = category_service.get_categories(platform)

    tree = []
    category_map = {cat["id"]: {**cat, "children": []} for cat in categories}

    for cat in categories:
        if cat["parent_id"] and cat["parent_id"] in category_map:
            category_map[cat["parent_id"]]["children"].append(category_map[cat["id"]])
        elif not cat["parent_id"]:
            tree.append(category_map[cat["id"]])

    return {"success": True, "tree": tree}


@router.post("/categories/{platform}/refresh")
def refresh_categories_with_api(
    platform: str,
    api_key: str,
    current_user: User = Depends(get_current_user),
):
    """Обновить справочник категорий с использованием API ключа"""
    categories = category_service.get_categories_with_api_key(platform, api_key)
    return {
        "success": True,
        "categories": categories,
        "total": len(categories),
        "source": "api" if api_key else "mock",
    }


# ========== Маппинг категорий ==========


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
    source_platform: str,
    source_category_id: str,
    target_platform: str,
    target_category_id: str,
    current_user: User = Depends(get_current_user),
):
    """Сохранить маппинг категории для текущего пользователя"""
    result = category_service.save_category_mapping(
        current_user.id,
        source_platform,
        source_category_id,
        target_platform,
        target_category_id,
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
        raise HTTPException(status_code=500, detail="Ошибка удаления маппинга")
    finally:
        db.close()