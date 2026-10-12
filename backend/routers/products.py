"""
Роутер для работы с товарами.
Поддерживает фильтрацию, сортировку, пагинацию, массовые операции и удаление.

✅ Исправлено:
  - SessionLocal импортируется корректно
  - ORM-модель Product импортируется из database.models
  - убраны дубли импортов
  - добавлены POST /products/bulk-delete и POST /products/delete-all
  - удаления логируются и пишутся в статистику
  - ✅ bulk_update пишет категорию в mapped_category (для экспорта), не в category
  - ✅ bulk_update валидирует категорию по спекам площадки
  - ✅ детальное логирование массовых операций
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.auth import get_current_user
from database.models import Product as ProductORM
from database.models import User
from database.repository import repo, stats_repo
from database.session import SessionLocal
from models.schemas import ProductBulkUpdate, ProductLogisticsUpdate, Stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Products"])

# Карта сортировок фронтенда -> (поле, направление) для репозитория
SORT_MAP = {
    "newest": ("created_at", "desc"),
    "oldest": ("created_at", "asc"),
    "name_asc": ("name", "asc"),
    "name_desc": ("name", "desc"),
    "price_asc": ("price", "asc"),
    "price_desc": ("price", "desc"),
}


# ==================== Схемы запросов удаления ====================


class BulkDeleteRequest(BaseModel):
    product_ids: list[int]


class DeleteAllRequest(BaseModel):
    confirm: bool = False


# ==================== Хелпер: валидация категории по спекам ====================


def _validate_category_against_specs(category_name: str) -> dict:
    """
    Проверяет, существует ли ТОЧНОЕ имя категории в platform_category_specs
    хотя бы для одной из площадок.

    Возвращает:
        {"exists": True, "platforms": ["ozon", "wb"]} — если есть в спеках
        {"exists": False, "platforms": []} — если не нашлась ни в одной площадке
    """
    if not category_name:
        return {"exists": False, "platforms": []}

    from database.models import PlatformCategorySpec

    db = SessionLocal()
    try:
        rows = (
            db.query(PlatformCategorySpec.platform)
            .filter(PlatformCategorySpec.category_name == category_name.strip())
            .distinct()
            .all()
        )
        platforms = [r[0] for r in rows]
        return {"exists": len(platforms) > 0, "platforms": platforms}
    except Exception as e:
        logger.warning(f"Не удалось проверить категорию '{category_name}' по спекам: {e}")
        return {"exists": True, "platforms": ["?"]}  # при ошибке не блокируем
    finally:
        db.close()


# ==================== МАССОВЫЕ ОПЕРАЦИИ ====================


@router.put("/products/bulk-update")
def bulk_update_products(
    request: ProductBulkUpdate,
    current_user: User = Depends(get_current_user),
):
    """
    Массовое обновление цены/бренда/категории назначения для выбранных товаров.

    ✅ Категория назначения пишется в mapped_category (для экспорта), а не в category.
    Миграция подхватывает её по приоритету 2 цепочки.
    """
    if not request.product_ids or len(request.product_ids) == 0:
        raise HTTPException(status_code=400, detail="Не указаны товары для обновления")

    if all(
        v is None for v in (request.price, request.price_percent, request.brand, request.category)
    ):
        raise HTTPException(status_code=400, detail="Не указаны поля для обновления")

    # ✅ Валидация категории назначения по спекам (не блокирующая)
    category_warning = None
    if request.category is not None and request.category.strip():
        spec_check = _validate_category_against_specs(request.category)
        if not spec_check["exists"]:
            category_warning = (
                f"Категория «{request.category}» не найдена в спеках ни одной площадки. "
                f"Миграция завершится ошибкой для этих товаров."
            )
            logger.warning(f"⚠️ {category_warning}")
        else:
            logger.info(
                f"✅ Категория «{request.category}» есть в спеках площадок: "
                f"{', '.join(spec_check['platforms'])}"
            )

    updated = 0
    updated_ids: list[int] = []
    user_id = current_user.id

    for pid in request.product_ids:
        p = repo.get_by_id(pid, user_id=user_id)
        if not p:
            logger.debug(f"⏭ Товар {pid} пропущен: не принадлежит пользователю {user_id}")
            continue

        upd = {}

        # --- Цена ---
        if request.price_percent is not None:
            base_price = float(p["price"] or 0)
            upd["price"] = round(base_price * (1 + request.price_percent / 100), 2)
        elif request.price is not None:
            upd["price"] = float(request.price)

        # --- Бренд ---
        if request.brand is not None:
            upd["brand"] = request.brand.strip() or None

        # --- ✅ Категория назначения (в mapped_category, не в category) ---
        if request.category is not None:
            upd["mapped_category"] = request.category.strip() or None

        if upd:
            repo.update(pid, upd, user_id=user_id)
            updated += 1
            updated_ids.append(pid)

        # ✅ Список изменённых полей считаем отдельно — выражения f-string
    #    не могут продолжаться в соседнем строковом литерале
    changed_fields = [
        name
        for name in ("price", "price_percent", "brand", "category")
        if getattr(request, name, None) is not None
    ]
    logger.warning(
        f"✏️ Bulk update: user={current_user.id} "
        f"updated={updated}/{len(request.product_ids)} fields={changed_fields}"
    )

    try:
        stats_repo.record(
            user_id=current_user.id,
            operation="bulk_update",
            platform=None,
            status="success",
            total_items=len(request.product_ids),
            success_items=updated,
            failed_items=len(request.product_ids) - updated,
            duration_ms=0,
        )
    except Exception:
        pass

    return {
        "success": True,
        "updated": updated,
        "updated_ids": updated_ids,
        "category_warning": category_warning,
    }


@router.post("/products/bulk-delete")
def bulk_delete_products(
    payload: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Массовое удаление товаров.
    Пользователь удаляет только свои; админ — любые.
    ORM-cascade удаляет атрибуты и варианты вместе с товаром.
    """
    if not payload.product_ids or len(payload.product_ids) == 0:
        raise HTTPException(status_code=400, detail="Не указаны товары для удаления")

    db = SessionLocal()
    try:
        q = db.query(ProductORM).filter(ProductORM.id.in_(payload.product_ids))
        if current_user.role != "admin":
            q = q.filter(ProductORM.user_id == current_user.id)
        products = q.all()

        for p in products:
            db.delete(p)
        db.commit()

        deleted = len(products)
        skipped = len(payload.product_ids) - deleted

        logger.warning(
            f"🗑 Bulk delete: user={current_user.id} deleted={deleted} "
            f"requested={len(payload.product_ids)} skipped={skipped}"
        )
        try:
            stats_repo.record(
                user_id=current_user.id,
                operation="delete",
                platform=None,
                status="success",
                total_items=len(payload.product_ids),
                success_items=deleted,
                failed_items=skipped,
                duration_ms=0,
            )
        except Exception:
            pass

        return {"success": True, "deleted": deleted, "skipped": skipped}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка bulk-удаления: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления товаров")
    finally:
        db.close()


@router.post("/products/delete-all")
def delete_all_products(
    payload: DeleteAllRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Удалить ВСЕ товары: пользователь — свои, админ — все в системе.
    Требует явного подтверждения confirm=true (UI спрашивает слово «УДАЛИТЬ»).
    """
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Операция необратима. Передайте confirm=true для подтверждения.",
        )

    db = SessionLocal()
    try:
        q = db.query(ProductORM)
        if current_user.role != "admin":
            q = q.filter(ProductORM.user_id == current_user.id)
        products = q.all()

        for p in products:
            db.delete(p)
        db.commit()

        logger.warning(
            f"🗑 DELETE ALL: user={current_user.id} role={current_user.role} "
            f"deleted={len(products)}"
        )
        try:
            stats_repo.record(
                user_id=current_user.id,
                operation="delete_all",
                platform=None,
                status="success",
                total_items=len(products),
                success_items=len(products),
                failed_items=0,
                duration_ms=0,
            )
        except Exception:
            pass

        return {"success": True, "deleted": len(products)}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка полного удаления: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления товаров")
    finally:
        db.close()


# ==================== ЧТЕНИЕ ====================


@router.get("/products")
def get_products(
    search: str | None = Query(None, description="Поиск по названию, SKU, артикулу"),
    status: str | None = Query(
        None, description="Статус: pending | processing | success | error | all"
    ),
    source: str | None = Query(None, description="Источник импорта | all"),
    sort: str = Query(
        "newest",
        description="Сортировка: newest | oldest | name_asc | name_desc | price_asc | price_desc",
    ),
    skip: int = Query(0, ge=0, description="Смещение для пагинации"),
    limit: int = Query(50, ge=1, le=10000, description="Количество товаров на странице"),
    current_user: User = Depends(get_current_user),
):
    """
    Получить товары с фильтрацией, сортировкой и пагинацией.

    Контракт с фронтендом:
      - `status=all` и `source=all` означают "без фильтра"
      - `sort` принимает значения из SORT_MAP
      - `limit` ограничен 500 сверху (для UI-селекта 25/50/100/200)
    """
    is_admin = current_user.role == "admin"

    norm_status = None if (status in (None, "all", "")) else status
    norm_source = None if (source in (None, "all", "")) else source
    sort_by, sort_order = SORT_MAP.get(sort, SORT_MAP["newest"])
    norm_search = search.strip() if search and search.strip() else None

    return repo.get_all(
        user_id=current_user.id,
        is_admin=is_admin,
        search=norm_search,
        status=norm_status,
        source=norm_source,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=limit,
    )


@router.get("/stats", response_model=Stats)
def get_stats(current_user: User = Depends(get_current_user)):
    """Получить статистику по товарам текущего пользователя (или все для админа)."""
    is_admin = current_user.role == "admin"
    return repo.get_stats(user_id=current_user.id, is_admin=is_admin)


# ==================== ОДИНОЧНЫЕ ОПЕРАЦИИ ====================


@router.put("/products/{product_id}/logistics")
def update_product_logistics(
    product_id: int,
    payload: ProductLogisticsUpdate,
    current_user: User = Depends(get_current_user),
):
    """Логистические данные товара: штрихкод, габариты упаковки, НДС, ОКПД."""
    db = SessionLocal()
    try:
        product = (
            db.query(ProductORM)
            .filter(ProductORM.id == product_id, ProductORM.user_id == current_user.id)
            .first()
        )
        if not product:
            raise HTTPException(status_code=404, detail="Товар не найден")

        updates = payload.model_dump(exclude_unset=True)
        logger.warning(f"📦 logistics PUT id={product_id} user={current_user.id} updates={updates}")

        if not updates:
            logger.warning(
                f"📦 logistics PUT id={product_id}: payload пустой — ничего не сохраняем"
            )
            return {"success": True, "product_id": product.id, "updated_fields": 0}

        for field, value in updates.items():
            if not hasattr(product, field):
                logger.error(f"❌ Поле {field} отсутствует в модели Product!")
                continue
            setattr(product, field, value)
        db.commit()

        db.refresh(product)
        logger.warning(
            f"📦 logistics SAVED id={product_id}: "
            f"vat={product.vat_rate} okpd={product.okpd_code} "
            f"pkg_w={product.package_weight_grams} pkg_wxhxl="
            f"({product.package_width_mm}x{product.package_height_mm}x{product.package_length_mm}) "
            f"barcode={product.barcode}"
        )

        return {
            "success": True,
            "product_id": product.id,
            "updated_fields": len(updates),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ошибка обновления логистики товара {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обновления логистики: {e}")
    finally:
        db.close()


@router.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
):
    """Удалить товар (только если он принадлежит текущему пользователю; админ — любой)."""
    user_id = None if current_user.role == "admin" else current_user.id

    if repo.delete(product_id, user_id=user_id):
        logger.warning(f"🗑 Delete product {product_id} by user={current_user.id}")
        try:
            stats_repo.record(
                user_id=current_user.id,
                operation="delete",
                platform=None,
                status="success",
                total_items=1,
                success_items=1,
                failed_items=0,
                duration_ms=0,
            )
        except Exception:
            pass
        return {"success": True}
    raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")
