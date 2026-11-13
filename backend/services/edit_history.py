"""
Аудит-лог правок товаров + undo (обобщение BulkEditSnapshot).

Каждая операция правки (массовое обновление, одиночная правка, логистика,
массовый подбор ТН ВЭД, дозаполнение дефолтами) пишет снапшот прежних
значений затронутых полей. Отсюда:
  * write_edit_snapshot() — вызвать ДО применения изменений (в той же транзакции);
  * undo_snapshot()       — восстановить значения выбранного/последнего снапшота;
  * list_edit_history()  — лента последних операций для UI.

Ротация: храним последние SNAPSHOTS_PER_USER строк на пользователя.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BulkEditSnapshot, Product
from services.bulk_ops import apply_snapshot, build_snapshot_payload

logger = logging.getLogger(__name__)

# Сколько последних операций держим в истории/для undo (ротация старых)
SNAPSHOTS_PER_USER = 20


async def write_edit_snapshot(
    db: AsyncSession,
    user_id: int,
    products: list[Any],
    fields: list[str],
    action: str = "edit",
    label: str | None = None,
) -> BulkEditSnapshot | None:
    """
    Снапшот ТЕКУЩИХ значений перечисленных полей ДО изменения.

    Вызывать в той же транзакции, что и правку, ДО setattr'ов.
    products — ORM-объекты Product (или достаточно атрибутов id + полей).
    Возвращает созданный снапшот (или None, если полей/товаров нет).
    Ротация старых выполняется здесь же (отдельный commit делает роутер).
    """
    if not products or not fields:
        return None

    payload = build_snapshot_payload(products, fields)
    if not payload["items"] or not payload["fields"]:
        return None

    snap = BulkEditSnapshot(
        user_id=user_id,
        action=action,
        label=(label or "")[:300] or None,
        payload=payload,
    )
    db.add(snap)
    await db.flush()  # чтобы получить snap.id для ротации

    # Ротация: оставляем последние SNAPSHOTS_PER_USER (включая только что созданный)
    old_ids = (
        (
            await db.execute(
                select(BulkEditSnapshot.id)
                .where(BulkEditSnapshot.user_id == user_id)
                .order_by(BulkEditSnapshot.id.desc())
                .offset(SNAPSHOTS_PER_USER)
            )
        )
        .scalars()
        .all()
    )
    if old_ids:
        await db.execute(delete(BulkEditSnapshot).where(BulkEditSnapshot.id.in_(old_ids)))

    logger.info(f"📋 snapshot: user={user_id} action={action} items={len(payload['items'])}")
    return snap


async def undo_snapshot(db: AsyncSession, user_id: int, snapshot_id: int | None = None) -> dict:
    """
    Отменить операцию правки: восстановить прежние значения полей.

    Без snapshot_id — последний НЕотменённый снапшот пользователя.
    Отменённые снапшоты не удаляются (остаются в истории), но повторно
    отменить их нельзя.
    """
    stmt = select(BulkEditSnapshot).where(BulkEditSnapshot.user_id == user_id)
    if snapshot_id is not None:
        stmt = stmt.where(BulkEditSnapshot.id == snapshot_id)
    else:
        stmt = stmt.where(BulkEditSnapshot.undone.is_(False))
    snapshot = (
        await db.execute(stmt.order_by(BulkEditSnapshot.id.desc()).limit(1))
    ).scalar_one_or_none()

    if snapshot is None:
        return {"success": False, "detail": "Нет изменений, доступных для отмены"}

    if snapshot.undone:
        return {"success": False, "detail": "Эта операция уже отменена"}

    ids = [item.get("id") for item in snapshot.payload.get("items", []) if item.get("id")]
    products = (
        (await db.execute(select(Product).where(Product.id.in_(ids), Product.user_id == user_id)))
        .scalars()
        .all()
        if ids
        else []
    )

    result = apply_snapshot({p.id: p for p in products}, snapshot.payload)
    snapshot.undone = True
    await db.flush()

    logger.info(
        f"↩️ undo: user={user_id} snapshot={snapshot.id} action={snapshot.action} "
        f"restored={result['restored']} skipped_missing={result['skipped_missing']}"
    )
    return {
        "success": True,
        "restored": result["restored"],
        "skipped_missing": result["skipped_missing"],
        "fields": result["fields"],
        "action": snapshot.action,
        "label": snapshot.label,
        "snapshot_id": snapshot.id,
    }


async def list_edit_history(db: AsyncSession, user_id: int, limit: int = 20) -> dict:
    """
    Лента последних операций правки для UI («История изменений»).
    undone=True — операция была отменена (показываем приглушённо).
    """
    rows = (
        (
            await db.execute(
                select(BulkEditSnapshot)
                .where(BulkEditSnapshot.user_id == user_id)
                .order_by(BulkEditSnapshot.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    history = []
    for s in rows:
        payload = s.payload or {}
        history.append(
            {
                "id": s.id,
                "action": s.action,
                "label": s.label,
                "fields": payload.get("fields", []),
                "items_count": len(payload.get("items", [])),
                "undone": bool(s.undone),
                "created_at": s.created_at.isoformat() + "Z" if s.created_at else None,
            }
        )
    return {"history": history, "has_undo": any(not h["undone"] for h in history)}
