"""Внутренние хелперы пакета категорий.

Вынесено из монолита routers/categories.py (Р7).
"""

import logging

from fastapi import HTTPException
from pydantic import BaseModel

from database.models import User

logger = logging.getLogger(__name__)


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


def _public_task_info(info: dict) -> dict:
    """Копия инфо задачи для API-ответа: без внутренностей (enc_key, done_keys)."""
    public = dict(info)
    public.pop("resume_params", None)
    public.pop("done_keys", None)
    return public
