"""
Роутер для управления характеристиками товаров.

✅ Шаг 2.7: автоматическая нормализация регистра значений по словарям площадок.
Ozon чувствителен к регистру: «белый» ≠ «Белый» → ошибка «Такой товар уже существует»
и создание дубля. При сохранении значение приводится к регистру словаря площадки.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import get_current_user
from database.models import PlatformCategorySpec, User
from database.repository import attr_repo, repo
from database.session import SessionLocal
from services.attribute_normalizer import normalize_attributes

router = APIRouter(prefix="/api/products", tags=["Attributes"])

# Приоритет платформ при поиске спека для нормализации
PLATFORM_PRIORITY = ["ozon", "yandex", "wildberries"]


class AttributeCreate(BaseModel):
    name: str
    value: str
    platform_attribute_id: str | None = None


class AttributeUpdate(BaseModel):
    name: str
    value: str
    platform_attribute_id: str | None = None


class BulkAttributesUpdate(BaseModel):
    """Массовое обновление характеристик для группы товаров"""

    product_ids: list[int]
    attributes: list[AttributeUpdate]  # набор характеристик для всех товаров


# ==================== Вспомогательные функции нормализации ====================


def _product_category(product) -> str | None:
    """Категория товара (dict или ORM-объект)."""
    if isinstance(product, dict):
        return product.get("mapped_category") or product.get("category")
    return getattr(product, "mapped_category", None) or getattr(product, "category", None)


def _get_spec_for_category(user_id: int, category_name: str | None) -> dict | None:
    """
    Ищет спек категории (словари значений атрибутов) среди загруженных спеков.
    Если категория есть в спеках нескольких платформ — берём по приоритету.
    """
    if not category_name:
        return None
    db = SessionLocal()
    try:
        rows = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.category_name == category_name,
            )
            .all()
        )
        if not rows:
            return None
        by_platform = {r.platform: r.spec for r in rows}
        for p in PLATFORM_PRIORITY:
            if p in by_platform:
                return by_platform[p]
        return rows[0].spec
    finally:
        db.close()


# ==================== Эндпоинты ====================


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
    attributes: list[AttributeUpdate],
    current_user: User = Depends(get_current_user),
):
    """Заменить все характеристики товара на новые (с нормализацией регистра)."""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    spec = _get_spec_for_category(current_user.id, _product_category(product))
    raw_attrs = [a.model_dump() for a in attributes]
    norm = normalize_attributes(raw_attrs, spec)

    result = attr_repo.set_attributes(product_id, norm["normalized_attributes"])
    return {
        "success": True,
        "attributes": result,
        "count": len(result),
        "normalizations": norm["normalizations"],  # ✅ что было приведено к словарю
        "warnings": norm["warnings"],  # ✅ значения не из словаря
    }


@router.post("/{product_id}/attributes")
def add_attribute(
    product_id: int,
    attribute: AttributeCreate,
    current_user: User = Depends(get_current_user),
):
    """Добавить одну характеристику к товару (с нормализацией регистра)."""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    spec = _get_spec_for_category(current_user.id, _product_category(product))
    norm = normalize_attributes([attribute.model_dump()], spec)
    na = norm["normalized_attributes"][0]

    result = attr_repo.add_attribute(
        product_id=product_id,
        name=na["name"],
        value=na["value"],
        platform_attribute_id=na.get("platform_attribute_id"),
    )
    return {
        "success": True,
        "attribute": result,
        "normalizations": norm["normalizations"],
        "warnings": norm["warnings"],
    }


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
    """
    Массовая установка характеристик для нескольких товаров.
    ✅ Нормализация per-product: товары могут быть из разных категорий → разные словари.
    """
    if not payload.product_ids:
        raise HTTPException(status_code=400, detail="Не указаны товары")

    raw_attrs = [a.model_dump() for a in payload.attributes]
    updated = 0
    all_normalizations = []
    all_warnings = []

    for pid in payload.product_ids:
        product = repo.get_by_id(pid, user_id=current_user.id)
        if not product:
            continue
        spec = _get_spec_for_category(current_user.id, _product_category(product))
        norm = normalize_attributes(raw_attrs, spec)
        attr_repo.set_attributes(pid, norm["normalized_attributes"])
        all_normalizations.extend(norm["normalizations"])
        all_warnings.extend(norm["warnings"])
        updated += 1

    return {
        "success": True,
        "updated": updated,
        "normalizations": all_normalizations[:20],  # ограничиваем размер ответа
        "warnings": all_warnings[:20],
    }
