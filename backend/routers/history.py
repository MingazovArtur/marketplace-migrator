"""
Роутер истории операций (импорт/экспорт/миграции)
"""
from fastapi import APIRouter, Depends, Query
from database.repository import op_log
from database.models import User
from core.auth import get_current_user

router = APIRouter(prefix="/api", tags=["History"])


@router.get("/history")
def get_history(
    operation: str = Query(None, description="import | export | migration | None (все)"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
):
    """Единая лента истории операций текущего пользователя (админ видит всё)."""
    is_admin = current_user.role == "admin"
    entries = op_log.get_history(
        user_id=current_user.id,
        is_admin=is_admin,
        operation=operation,
        limit=limit,
        skip=skip,
    )
    return {"success": True, "history": entries, "total": len(entries)}