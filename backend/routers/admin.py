"""Админ-панель: управление пользователями, общая статистика, журнал доступа.

Все эндпоинты закрыты dependency get_current_admin_user — роль читается
из БД на каждом запросе, поэтому понижение роли применяется мгновенно
и не зависит от содержимого JWT (асимметрия из R-35 В-9).

Изменения пользователей пишутся в журнал доступа (152-ФЗ) с двух
сторон: кто менял и кого меняли — суть изменения попадает в запись
администратора (в схеме журнала отдельного поля «детали» нет).
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_

from core.auth import get_current_admin_user
from core.time import utcnow
from database.access_log import get_client_ip, log_access
from database.models import AccessLog, ImportExportStats, MigrationLog, Product, User
from database.session import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin"])

VALID_ROLES = {"user", "admin"}
_LOGIN_ACTIONS = ("login_success", "demo_login")


class AdminUserUpdate(BaseModel):
    """Изменение пользователя от имени админа: роль и/или активность."""

    role: str | None = None
    is_active: bool | None = None


def _user_dict(u: User, *, products_count: int | None = None, last_login_at=None) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "role": u.role,
        "is_active": bool(u.is_active),
        "email_verified": bool(u.email_verified_at),
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "products_count": products_count,
        "last_login_at": last_login_at.isoformat() if last_login_at else None,
    }


@router.get("/users")
def list_users(
    search: str = Query("", max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user),
):
    """Список пользователей с числом товаров и временем последнего входа."""
    db = SessionLocal()
    try:
        q = db.query(User)
        if search.strip():
            like = f"%{search.strip()}%"
            q = q.filter(or_(User.username.ilike(like), User.email.ilike(like)))

        total = q.count()
        users = q.order_by(User.id).offset(skip).limit(limit).all()

        product_counts: dict = {}
        last_logins: dict = {}
        user_ids = [u.id for u in users]
        if user_ids:
            product_counts = dict(
                db.query(Product.user_id, func.count(Product.id))
                .filter(Product.user_id.in_(user_ids))
                .group_by(Product.user_id)
                .all()
            )
            last_logins = dict(
                db.query(AccessLog.user_id, func.max(AccessLog.created_at))
                .filter(
                    AccessLog.user_id.in_(user_ids),
                    AccessLog.action.in_(_LOGIN_ACTIONS),
                )
                .group_by(AccessLog.user_id)
                .all()
            )

        return {
            "success": True,
            "total": total,
            "users": [
                _user_dict(
                    u,
                    products_count=int(product_counts.get(u.id, 0)),
                    last_login_at=last_logins.get(u.id),
                )
                for u in users
            ],
        }
    finally:
        db.close()


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
):
    """Смена роли и/или активности пользователя.

    Защита от само-блокировки: собственную роль и активность менять нельзя.
    Деактивация применяется мгновенно — get_current_user отклоняет токены
    неактивных пользователей на каждом запросе (R-35, К-3).
    """
    if payload.role is None and payload.is_active is None:
        raise HTTPException(status_code=400, detail="Не указаны изменения (role или is_active)")
    if payload.role is not None and payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="role должен быть 'user' или 'admin'")

    db = SessionLocal()
    try:
        target = db.query(User).filter(User.id == user_id).first()
        if target is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if target.id == current_user.id:
            raise HTTPException(
                status_code=400,
                detail="Нельзя менять собственную роль/активность — можно остаться без админов",
            )

        changed = []
        if payload.role is not None and payload.role != target.role:
            target.role = payload.role
            changed.append(f"role={payload.role}")
        if payload.is_active is not None and bool(payload.is_active) != bool(target.is_active):
            target.is_active = bool(payload.is_active)
            changed.append(f"is_active={payload.is_active}")

        if not changed:
            return {"success": True, "user": _user_dict(target), "changed": []}

        db.commit()
        db.refresh(target)

        # Аудит (152-ФЗ): запись у администратора (кто + что сделал),
        # запись у цели (кого меняли). Суть — в user_agent-поле записи админа.
        ip = get_client_ip(request)
        ua = request.headers.get("user-agent") or ""
        detail = "; ".join(changed)
        log_access(
            user_id=current_user.id,
            username=current_user.username,
            action="admin_update_user",
            ip=ip,
            user_agent=f"{ua} | -> user#{target.id}({target.username}): {detail}",
        )
        log_access(
            user_id=target.id,
            username=target.username,
            action="admin_update_user",
            ip=ip,
            user_agent=f"{ua} | by admin#{current_user.id}({current_user.username})",
        )
        logger.info(f"admin {current_user.username} обновил user#{target.id}: {detail}")

        return {"success": True, "user": _user_dict(target), "changed": changed}
    finally:
        db.close()


@router.get("/stats")
def admin_stats(current_user: User = Depends(get_current_admin_user)):
    """Сводка по всему сервису: пользователи, товары, миграции, активность."""
    db = SessionLocal()
    try:
        since_7d = utcnow() - timedelta(days=7)

        users_total = db.query(func.count(User.id)).scalar() or 0
        new_users_7d = (
            db.query(func.count(User.id)).filter(User.created_at >= since_7d).scalar() or 0
        )
        active_users_7d = (
            db.query(func.count(func.distinct(AccessLog.user_id)))
            .filter(
                AccessLog.user_id.isnot(None),
                AccessLog.created_at >= since_7d,
                AccessLog.action.in_(_LOGIN_ACTIONS),
            )
            .scalar()
            or 0
        )
        products_total = db.query(func.count(Product.id)).scalar() or 0
        migrations_total = db.query(func.count(MigrationLog.id)).scalar() or 0
        operations_7d = (
            db.query(func.count(ImportExportStats.id))
            .filter(ImportExportStats.created_at >= since_7d)
            .scalar()
            or 0
        )
        platforms_7d = (
            db.query(ImportExportStats.platform, func.count(ImportExportStats.id))
            .filter(
                ImportExportStats.created_at >= since_7d,
                ImportExportStats.platform.isnot(None),
            )
            .group_by(ImportExportStats.platform)
            .all()
        )

        return {
            "success": True,
            "users_total": int(users_total),
            "new_users_7d": int(new_users_7d),
            "active_users_7d": int(active_users_7d),
            "products_total": int(products_total),
            "migrations_total": int(migrations_total),
            "operations_7d": int(operations_7d),
            "platforms_7d": [
                {"platform": p, "count": int(c)}
                for p, c in sorted(platforms_7d, key=lambda r: -r[1])
            ],
        }
    finally:
        db.close()


@router.get("/access-logs")
def access_logs(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_admin_user),
):
    """Последние записи журнала доступа (кто/когда/откуда)."""
    db = SessionLocal()
    try:
        rows = db.query(AccessLog).order_by(AccessLog.id.desc()).limit(limit).all()
        return {
            "success": True,
            "logs": [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "username": r.username,
                    "action": r.action,
                    "ip": r.ip,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()
