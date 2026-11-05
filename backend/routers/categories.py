"""
Роутер для работы со справочниками категорий и маппингом.

✅ Изменения:
  - добавлен GET /specs/{platform}/names — лёгкий список имён (для datalist)[cite: 10]
  - порядок маршрутов: /names объявлен ДО /{category_id:path} (иначе "names" ловится как id)[cite: 10]
  - детализация: key-source теперь отдаёт also `hint` — что делать если ключа нет[cite: 10]
  - ИНТЕГРАЦИЯ КЭША: /specs/{platform}/names и /categories/{platform} используют Redis[cite: 10]
  - /categories/{platform}/refresh и /category-mapping принимают как JSON body, так и query-параметры[cite: 10]
  - /{category_id:path} корректно принимает названия со слэшами («Родитель / Тип») и ищет по category_id ИЛИ category_name
  - добавлены DELETE /specs/{platform} и DELETE /specs/{platform}/{category_id:path} для администратора
  - ЕДИНЫЙ ФОРМАТ ЗАГРУЗКИ СПЕКОВ: Ozon, Яндекс Маркет и Wildberries запускаются в фоне через Celery (refresh_specs_task) и отдают прогресс через /specs/{platform}/refresh/{task_id}/progress
"""

import logging
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_

from core.auth import get_current_user
from core.config import settings
from core.crypto import encrypt_str
from database.models import CategoryMapping, PlatformCategorySpec, User
from database.session import SessionLocal
from models.schemas import (
    PlatformCategorySpecResponse,
    RefreshSpecRequest,
)
from services import cache_service, specs_monitor
from services.category_service import category_service
from tasks import get_progress, refresh_specs_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Categories"])


class RefreshCategoriesPayload(BaseModel):
    api_key: str = ""


class SaveMappingPayload(BaseModel):
    source_platform: str | None = None
    source_category_id: str | None = None
    target_platform: str | None = None
    target_category_id: str | None = None


def _require_admin(user: User) -> None:
    if getattr(user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Доступ только для администратора")


# ===========================================================================
# Спецификации категорий площадок
# ===========================================================================


@router.post("/specs/{platform}/refresh")
async def refresh_specs(
    platform: str,
    payload: RefreshSpecRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Единый формат обновления спецификаций категорий площадки через её API.
    Для всех поддерживаемых площадок (Ozon, Яндекс Маркет, Wildberries) запускает
    фоновую задачу Celery и возвращает task_id для отслеживания прогресса
    через /specs/{platform}/refresh/{task_id}/progress.
    """
    platform = platform.lower().strip()
    if platform not in ("ozon", "yandex", "wildberries"):
        raise HTTPException(status_code=501, detail=f"Загрузчик для {platform} ещё не реализован")

    raw_key = (payload.api_key or "").strip()
    business_id = (str(payload.business_id).strip() if payload.business_id else "")

    # Если для Ozon переданы раздельно business_id (как Client ID) и api_key (как UUID)
    if platform == "ozon" and raw_key and ":" not in raw_key and business_id:
        raw_key = f"{business_id}:{raw_key}"

    if not raw_key and platform == "ozon" and settings.OZON_CLIENT_ID and settings.OZON_API_KEY:
        raw_key = f"{settings.OZON_CLIENT_ID}:{settings.OZON_API_KEY}"

    if not raw_key:
        raise HTTPException(status_code=400, detail="Не указан API-ключ площадки")

    if platform == "yandex" and not business_id:
        raise HTTPException(
            status_code=400,
            detail="Для Яндекс Маркета укажите номер кабинета (ID кабинета / business_id) и OAuth-токен",
        )

    try:
        cache_service.delete_pattern(f"specs:{platform}:*")

        # В-4 (неделя 2): ключ шифруется перед публикацией в Redis —
        # в брокере не остаётся plaintext API-ключей (decrypt — в воркере).
        # Тот же шифротекст сохраняется в реестре мониторинга, чтобы админ
        # мог продолжить остановленную загрузку без повторного ввода ключа.
        enc_key = encrypt_str(raw_key)

        task = refresh_specs_task.delay(
            user_id=current_user.id,
            platform=platform,
            raw_api_key=enc_key,
            category_ids=payload.category_ids,
            business_id=business_id or None,
        )
        # Реестр мониторинга (админ-страница): задача сразу видна как «в очереди» —
        # до этого параллельные загрузки в solo-воркере были невидимы
        specs_monitor.register(
            task.id,
            platform=platform,
            user_id=current_user.id,
            username=current_user.username,
            resume_params={
                "enc_key": enc_key,
                "category_ids": payload.category_ids,
                "business_id": business_id or None,
                "skip_category_ids": [],
            },
        )
        logger.info(f"Specs refresh queued [{platform}]: task_id={task.id}, user={current_user.id}")
        return {
            "success": True,
            "task_id": task.id,
            "platform": platform,
            "message": f"Загрузка спецификаций {platform} запущена в фоне",
        }

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
    """Прогресс фоновой загрузки спеков (единый формат для всех площадок)."""
    return get_progress(task_id)


def _public_task_info(info: dict) -> dict:
    """Копия инфо задачи для API-ответа: без внутренностей (enc_key, done_keys)."""
    public = dict(info)
    public.pop("resume_params", None)
    public.pop("done_keys", None)
    return public


@router.get("/admin/specs-tasks")
def admin_specs_tasks(current_user: User = Depends(get_current_user)):
    """
    Мониторинг загрузок спеков (только админ).

    Активные (в очереди / в работе) с живым прогрессом из Celery
    + последние завершённые (успех/ошибки/длительность/пауза).
    """
    _require_admin(current_user)

    active = []
    for info in specs_monitor.list_active():
        live = get_progress(info.get("task_id", ""))
        live_percent = int(live.get("percent") or 0)
        in_progress = live.get("status") == "progress"
        pause_requested = bool(info.get("pause_requested"))
        active.append(
            {
                "task_id": info.get("task_id"),
                "platform": info.get("platform"),
                "user_id": info.get("user_id"),
                "username": info.get("username"),
                "state": "running" if in_progress else info.get("state"),
                "enqueued_at": info.get("enqueued_at"),
                "started_at": info.get("started_at"),
                "percent": live_percent if in_progress else 0,
                "total": live.get("total", 0) if in_progress else 0,
                "success": live.get("success", 0) if in_progress else 0,
                "errors": live.get("errors", 0) if in_progress else 0,
                "stale": specs_monitor.is_stale(info, live_percent),
                "pause_requested": pause_requested,
                "can_pause": not pause_requested,
            }
        )

    history = []
    for info in specs_monitor.list_history(20):
        info = _public_task_info(info)
        info["can_resume"] = (
            info.get("status") in specs_monitor.RESUMABLE_STATUSES
            and not info.get("resumed_as")
        )
        history.append(info)

    return {
        "success": True,
        "active": active,
        "history": history,
    }


@router.post("/admin/specs-tasks/{task_id}/pause")
def admin_specs_task_pause(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Поставить загрузку спеков на паузу (только админ).

    Кооперативная остановка: задача проверяет флаг между блоками категорий,
    дообрабатывает текущий блок (прогресс коммитится в БД) и завершается
    со статусом paused. Стоящая в очереди задача снимается на старте —
    воркер освобождается для других работ. Возобновление — POST .../{task_id}/resume.
    """
    _require_admin(current_user)

    if not specs_monitor.request_pause(task_id):
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена или уже завершена",
        )
    logger.info(f"⏸ ADMIN PAUSE SPECS: user={current_user.id} task={task_id}")
    return {
        "success": True,
        "task_id": task_id,
        "message": (
            "Пауза запрошена: задача остановится после текущего блока категорий "
            "(стоящая в очереди — на старте). Продолжить можно кнопкой «Возобновить»"
        ),
    }


@router.post("/admin/specs-tasks/{task_id}/resume")
def admin_specs_task_resume(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Продолжить остановленную загрузку спеков (только админ).

    Работает и для «на паузе», и для «прервана» (воркер был перезапущен —
    docker compose down / crash: при старте спек-воркера такие записи
    помечаются interrupted, а прогресс закоммиченных категорий
    сохраняется в реестр во время загрузки). Ставит в очередь НОВУЮ задачу
    с теми же параметрами (ключ берётся из реестра — повторный ввод не нужен)
    и списком уже сохранённых категорий (skip_category_ids): загрузка
    продолжается с места остановки.
    """
    _require_admin(current_user)

    info = specs_monitor.get_info(task_id)
    if not info:
        raise HTTPException(status_code=404, detail="Задача не найдена в реестре мониторинга")
    if info.get("status") not in specs_monitor.RESUMABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Продолжить можно только задачу «на паузе» или «прерванную» "
            "(например, после перезапуска воркера)",
        )
    if specs_monitor.get_resumed(task_id):
        raise HTTPException(status_code=409, detail="Эта задача уже была продолжена")

    params = info.get("resume_params") or {}
    enc_key = params.get("enc_key")
    platform = info.get("platform")
    user_id = info.get("user_id")
    if not enc_key or not platform or not user_id:
        raise HTTPException(
            status_code=409,
            detail="Параметры запуска не сохранились (задача запущена до обновления) — "
            "запустите загрузку заново на странице «Спецификации»",
        )

    # Что уже в БД: категории этой загрузки + унаследованные из предыдущих поколений
    skip = sorted({str(k) for k in (info.get("done_keys") or [])} | {str(k) for k in (params.get("skip_category_ids") or [])})

    try:
        task = refresh_specs_task.delay(
            user_id=user_id,
            platform=platform,
            raw_api_key=enc_key,
            category_ids=params.get("category_ids"),
            business_id=params.get("business_id"),
            skip_category_ids=skip,
        )
    except Exception as e:
        logger.error(f"❌ Не удалось поставить продолжение задачи {task_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Не удалось поставить задачу в очередь: {e}")

    specs_monitor.register(
        task.id,
        platform=platform,
        user_id=user_id,
        username=info.get("username"),
        resume_params={
            "enc_key": enc_key,
            "category_ids": params.get("category_ids"),
            "business_id": params.get("business_id"),
            "skip_category_ids": skip,
        },
    )
    specs_monitor.mark_resumed(task_id, task.id)

    logger.info(
        f"▶ ADMIN RESUME SPECS: user={current_user.id} old_task={task_id} -> new_task={task.id} "
        f"[{platform}] пропустить {len(skip)} категорий"
    )
    return {
        "success": True,
        "task_id": task.id,
        "platform": platform,
        "skipped": len(skip),
        "message": f"Загрузка продолжена (пропущено уже сохранённых категорий: {len(skip)}). "
        "Новая задача видна в списке активных.",
    }


@router.get("/specs/{platform}/key-source")
def spec_key_source(platform: str, current_user: User = Depends(get_current_user)):
    """
    Индикатор: есть ли серверный ключ площадки в .env.
    При ошибке возвращает has_server_key=False + hint.
    """
    has_server_key = False
    hint = ""
    try:
        if platform == "ozon":
            client_id = getattr(settings, "OZON_CLIENT_ID", "") or ""
            api_key = getattr(settings, "OZON_API_KEY", "") or ""
            has_server_key = bool(client_id.strip() and api_key.strip())
            if not has_server_key:
                hint = "Задайте OZON_CLIENT_ID и OZON_API_KEY в .env или введите данные в форме"
    except Exception as e:
        logger.warning(f"key-source check failed for {platform}: {e}")
        has_server_key = False

    return {"platform": platform, "has_server_key": has_server_key, "hint": hint}


# ========== ВАЖНО: порядок маршрутов — /names ДО /{category_id:path} ==========


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


# ===========================================================================
# Справочники категорий
# ===========================================================================


@router.get("/categories/{platform}")
def get_categories(platform: str, force_refresh: bool = False):
    """
    Получить список категорий для платформы.
    КЭШИРУЕТСЯ на 2 часа, если не запрошен force_refresh.
    """
    cache_key = f"categories:{platform}:list"

    if not force_refresh:
        cached = cache_service.get(cache_key)
        if cached is not None:
            return {"success": True, "categories": cached, "total": len(cached), "from_cache": True}

    categories = category_service.get_categories(platform, force_refresh)
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
    api_key: str | None = Query(default=None),
    payload: RefreshCategoriesPayload | None = Body(default=None),
    current_user: User = Depends(get_current_user),
):
    """
    ✅ ИСПРАВЛЕНО: Обновить справочник категорий с использованием API ключа.
    Принимает api_key как из JSON-тела (от CategoryMapping.jsx), так и из query-параметра.
    """
    resolved_key = (api_key or (payload.api_key if payload else "") or "").strip()
    categories = category_service.get_categories_with_api_key(platform, resolved_key)

    cache_service.delete_pattern(f"categories:{platform}:*")

    return {
        "success": True,
        "categories": categories,
        "total": len(categories),
        "source": "api" if resolved_key else "mock",
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
        raise HTTPException(status_code=500, detail="Ошибка удаления маппинга")
    finally:
        db.close()