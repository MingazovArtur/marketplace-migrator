"""
Роутер для авто-подбора и поиска кодов ТН ВЭД.

✅ v4: массовый подбор — POST /batch-suggest (топ-коды по выбранным товарам)
и POST /batch-apply (проставить код всем выбранным; откатывается через undo).
"""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from database.models import Product, User
from database.session import get_async_db
from services.edit_history import write_edit_snapshot
from services.tnved_mapper import get_tnved_description, search_tnved, suggest_tnved

router = APIRouter(prefix="/api/tnved", tags=["ТН ВЭД"])

# Максимум товаров в одном пакетном запросе (защита от тяжёлых запросов)
BATCH_LIMIT = 500


@router.get("/suggest")
def suggest_tnved_endpoint(
    name: str = Query(..., description="Название товара для анализа"),
    category: str = Query("", description="Категория товара (опционально)"),
):
    """
    Авто-подбор кодов ТН ВЭД на основе названия и категории.
    Возвращает топ-3 наиболее вероятных вариантов.
    """
    suggestions = suggest_tnved(name, category)

    return {
        "success": True,
        "suggestions": suggestions,
        "message": f"Найдено {len(suggestions)} вариантов" if suggestions else "Точных совпадений не найдено. Проверьте название или категорию."
    }


@router.get("/search")
def search_tnved_endpoint(
    query: str = Query(..., min_length=2, description="Поисковый запрос (слово, часть кода или описание)"),
):
    """
    Поиск по справочнику ТН ВЭД по произвольному запросу.
    Возвращает до 10 релевантных записей.
    """
    results = search_tnved(query)

    return {
        "success": True,
        "results": results,
        "total": len(results)
    }


# ==================== Массовый подбор (v4) ====================


class TnvedBatchSuggestRequest(BaseModel):
    """Товары, для которых подобрать ТН ВЭД."""

    product_ids: list[int]

    @field_validator("product_ids")
    @classmethod
    def _check_ids(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("Список товаров пуст")
        if len(v) > BATCH_LIMIT:
            raise ValueError(f"Не более {BATCH_LIMIT} товаров за один запрос")
        return v


class TnvedBatchApplyRequest(TnvedBatchSuggestRequest):
    """Проставить выбранный код ТН ВЭД всем перечисленным товарам."""

    code: str


def _aggregate_codes(results: list[dict]) -> list[dict]:
    """Топ кодов по всем товарам: [{code, description, count, sample}] по убыванию."""
    counter: Counter[tuple[str, str]] = Counter()
    for r in results:
        for s in r.get("suggestions", []):
            counter[(s["code"], s["description"])] += 1
    return [
        {"code": code, "description": desc, "count": n}
        for (code, desc), n in counter.most_common(15)
    ]


@router.post("/batch-suggest")
async def tnved_batch_suggest(
    payload: TnvedBatchSuggestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Подбор ТН ВЭД сразу для списка товаров (авто-режим массовой модалки).

    Для каждого товара — топ-3 варианта по названию/категории; плюс агрегат:
    какие коды чаще всего подходят всей выборке (счётчик по товарам).
    """
    products = (
        (
            await db.execute(
                select(Product).where(
                    Product.id.in_(payload.product_ids),
                    Product.user_id == current_user.id,
                )
            )
        )
        .scalars()
        .all()
    )

    results = []
    for p in products:
        suggestions = suggest_tnved(p.name, p.category or "")
        results.append(
            {
                "product_id": p.id,
                "name": p.name,
                "category": p.category,
                "okpd_code": p.okpd_code,
                "suggestions": suggestions,
            }
        )

    with_suggestions = sum(1 for r in results if r["suggestions"])
    return {
        "success": True,
        "total": len(results),
        "with_suggestions": with_suggestions,
        "already_set": sum(1 for r in results if r["okpd_code"]),
        "results": results,
        "aggregated": _aggregate_codes(results),
    }


@router.post("/batch-apply")
async def tnved_batch_apply(
    payload: TnvedBatchApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Проставить выбранный код ТН ВЭД всем выбранным товарам.

    Пишет undo-снапшот прежних значений okpd_code — откатывается кнопкой
    «Отменить последнее изменение» (POST /products/bulk-undo).
    """
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Код ТН ВЭД не указан")

    products = (
        (
            await db.execute(
                select(Product).where(
                    Product.id.in_(payload.product_ids),
                    Product.user_id == current_user.id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not products:
        raise HTTPException(status_code=404, detail="Товары не найдены")

    # ✅ Undo-снапшот прежних значений okpd_code (ротация внутри сервиса)
    await write_edit_snapshot(
        db,
        current_user.id,
        list(products),
        ["okpd_code"],
        action="tnved",
        label=f"Массовый подбор ТН ВЭД: {code} ({len(products)} тов.)",
    )

    updated = 0
    for p in products:
        p.okpd_code = code
        updated += 1
    await db.commit()

    return {
        "success": True,
        "updated": updated,
        "code": code,
        "description": get_tnved_description(code),
        "undoable": True,
    }
