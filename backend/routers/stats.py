"""
Роутер статистики операций для дашборда.
"""

from fastapi import APIRouter, Depends, Query

from core.auth import get_current_user
from database.models import User
from database.repository import stats_repo

router = APIRouter(prefix="/api/stats", tags=["Stats"])


@router.get("/dashboard")
def dashboard(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
):
    """Сводная статистика операций за период (админ видит все данные)."""
    is_admin = current_user.role == "admin"
    data = stats_repo.get_dashboard(current_user.id, days=days, is_admin=is_admin)
    return {"success": True, **data}
