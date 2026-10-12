"""
Роутер для работы со справочниками категорий и маппингом.

✅ Изменения:
  - добавлен GET /specs/{platform}/names — лёгкий список имён (для datalist)
  - порядок маршрутов: /names объявлен ДО /{category_id} (иначе "names" ловится как id)
  - детализация: key-source теперь отдаёт also `hint` — что делать если ключа нет
  - ✅ ИНТЕГРАЦИЯ КЭША: /specs/{platform}/names и /categories/{platform} теперь используют Redis
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from core.auth import get_current_user
from core.config import settings
from database.models import CategoryMapping, PlatformCategorySpec, User
from database.session import SessionLocal
from models.schemas import (
    PlatformCategorySpecResponse,
    RefreshSpecRequest,
)
from services import cache_service  # ✅ Новый импорт
from services.category_service import category_service
from services.wb_specs import refresh_wildberries_specs
from services.yandex_specs import refresh_yandex_specs
from tasks import get_progress, refresh_specs_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Categories"])

# ===========================================================================
# Спецификации категорий площадок
# ===========================================================================


@router.post("/specs/{platform}/refresh")
async def refresh_specs(
    platform: str,
    payload: RefreshSpecRequest,
    current_user: User = Depends(get_current_user),  # ✅ ИСПРАВЛЕНО
):
    """
    Обновить спецификации категорий площадки через её API.
    ✅ Ozon — фоновая загрузка через Celery (8000+ категорий),
       возвращает task_id для polling через /specs/{platform}/refresh/{task_id}/progress.
    ✅ Yandex / WB — пока синхронно (они быстрее).
    """
    if platform not in ("ozon", "yandex", "wildberries"):
        raise HTTPException(status_code=501, detail=f"Загрузчик для {platform} ещё не реализован")

    raw_key = payload.api_key
    if not raw_key and platform == "ozon" and settings.OZON_CLIENT_ID and settings.OZON_API_KEY:
        raw_key = f"{settings.OZON_CLIENT_ID}:{settings.OZON_API_KEY}"

    if not raw_key:
        raise HTTPException(status_code=400, detail="Не указан API-ключ площадки")

    try:
        # ==================== OZON — фоновая загрузка ====================
        if platform == "ozon":
            # ✅ Сбрасываем кэш заранее, чтобы старые данные не показывались во время загрузки
            cache_service.delete_pattern(f"specs:{platform}:*")

            task = refresh_specs_task.delay(
                user_id=current_user.id,
                platform=platform,
                raw_api_key=raw_key,
                category_ids=payload.category_ids,
            )
            logger.info(f"Ozon specs refresh queued: task_id={task.id}, user={current_user.id}")
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
            # ✅ Инвалидация кэша после успешного обновления
            cache_service.delete_pattern(f"specs:{platform}:*")
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
        # ✅ Инвалидация кэша после успешного обновления
        cache_service.delete_pattern(f"specs:{platform}:*")
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
    """Прогресс фоновой загрузки спеков (единый формат с миграциями)."""
    return get_progress(task_id)


@router.get("/specs/{platform}/key-source")
def spec_key_source(platform: str, current_user: User = Depends(get_current_user)):
    """
    Индикатор: есть ли серверный ключ площадки в .env.
    ✅ При ошибке возвращает has_server_key=False + hint.
    """
    has_server_key = False
    hint = ""
    try:
        if platform == "ozon":
            client_id = getattr(settings, "OZON_CLIENT_ID", "") or ""
            api_key = getattr(settings, "OZON_API_KEY", "") or ""
            has_server_key = bool(client_id.strip() and api_key.strip())
            if not has_server_key:
                hint = "Задайте OZON_CLIENT_ID и OZON_API_KEY в .env или введите ключ в форме"
    except Exception as e:
        logger.warning(f"key-source check failed for {platform}: {e}")
        has_server_key = False

    return {"platform": platform, "has_server_key": has_server_key, "hint": hint}


# ========== ВАЖНО: порядок маршрутов — /names ДО /{category_id} ==========


@router.get("/specs/{platform}/names")
def list_spec_names(platform: str, current_user: User = Depends(get_current_user)):
    """
    ✅ ЛЁГКИЙ список имён категорий спеков (для datalist/автокомплита).
    Возвращает ТОЛЬКО имена (category_name), без атрибутов и словарей.
    Размер ответа ~50-150 КБ (vs 10+ МБ у полного /specs/{platform}).
    Используется в MigrateModal для выпадающего списка точных имён.
    ✅ КЭШИРУЕТСЯ на 1 час для снижения нагрузки на БД.
    """
    cache_key = f"specs:{platform}:names"

    # 1. Проверяем кэш
    cached = cache_service.get(cache_key)
    if cached is not None:
        return cached

    # 2. Если нет в кэше — идём в БД
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

        # 3. Сохраняем в кэш на 1 час (3600 сек)
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


@router.get("/specs/{platform}/{category_id}")
def get_spec(platform: str, category_id: str, current_user: User = Depends(get_current_user)):
    """Спек одной категории по её category_id."""
    db = SessionLocal()
    try:
        row = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == platform,
                PlatformCategorySpec.category_id == category_id,
            )
            .first()
        )
        if not row:
            raise HTTPException(
                status_code=404, detail="Спека не найдена. Сначала обновите через /refresh"
            )
        return PlatformCategorySpecResponse.model_validate(row)
    finally:
        db.close()


# ===========================================================================
# Справочники категорий
# ===========================================================================


@router.get("/categories/{platform}")
def get_categories(platform: str, force_refresh: bool = False):
    """
    Получить список категорий для платформы.
    ✅ КЭШИРУЕТСЯ на 2 часа, если не запрошен force_refresh.
    """
    cache_key = f"categories:{platform}:list"

    if not force_refresh:
        cached = cache_service.get(cache_key)
        if cached is not None:
            return {"success": True, "categories": cached, "total": len(cached), "from_cache": True}

    categories = category_service.get_categories(platform, force_refresh)

    # Сохраняем в кэш на 2 часа (7200 сек)
    cache_service.set(cache_key, categories, ttl=7200)

    return {
        "success": True,
        "categories": categories,
        "total": len(categories),
        "from_cache": False,
    }


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

    # ✅ Инвалидация кэша после ручного обновления
    cache_service.delete_pattern(f"categories:{platform}:*")

    return {
        "success": True,
        "categories": categories,
        "total": len(categories),
        "source": "api" if api_key else "mock",
    }


# ===========================================================================
# Маппинг категорий
# ===========================================================================


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
