"""
✅ v4: профили миграции — «площадка + дефолты» для типовых переносов в один клик.

CRUD + apply. Применение профиля проставляет сохранённые значения как
ГЛОБАЛЬНЫЕ дефолты пользователя (export_defaults, category_name=NULL) — их
подхватывают миграция (дозаполнение пустых полей) и кнопка «Заполнить пропуски».
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.platforms import Platform
from database.models import ExportDefault, MigrationProfile, User
from database.session import get_async_db
from services.edit_history import write_edit_snapshot  # noqa: F401 (зарезервировано)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/migration-profiles", tags=["Migration Profiles"])

# Те же поля дефолтов, что в ExportDefault (без category_name — профиль глобальный)
DEFAULTS_FIELDS = (
    "vat_rate",
    "okpd_code",
    "package_weight_grams",
    "package_width_mm",
    "package_height_mm",
    "package_length_mm",
    "brand",
    "marking",
    "price_default",
)

MAX_PROFILES_PER_USER = 20


class MigrationProfilePayload(BaseModel):
    name: str
    platform: str
    vat_rate: str | None = None
    okpd_code: str | None = None
    package_weight_grams: int | None = None
    package_width_mm: int | None = None
    package_height_mm: int | None = None
    package_length_mm: int | None = None
    brand: str | None = None
    marking: str | None = None
    price_default: float | None = None

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Название профиля не может быть пустым")
        return v

    @field_validator("platform")
    @classmethod
    def _platform_valid(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in Platform.all_values():
            raise ValueError(f"Неизвестная площадка: {v}")
        return v


def _row_to_dict(row: MigrationProfile) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "platform": row.platform,
        "vat_rate": row.vat_rate,
        "okpd_code": row.okpd_code,
        "package_weight_grams": row.package_weight_grams,
        "package_width_mm": row.package_width_mm,
        "package_height_mm": row.package_height_mm,
        "package_length_mm": row.package_length_mm,
        "brand": row.brand,
        "marking": row.marking,
        "price_default": float(row.price_default) if row.price_default is not None else None,
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
    }


@router.get("")
async def list_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    rows = (
        (
            await db.execute(
                select(MigrationProfile)
                .where(MigrationProfile.user_id == current_user.id)
                .order_by(MigrationProfile.name)
            )
        )
        .scalars()
        .all()
    )
    return {"profiles": [_row_to_dict(r) for r in rows]}


@router.post("")
async def save_profile(
    payload: MigrationProfilePayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Создать/обновить профиль (upsert по имени). Дефолты можно не передавать —
    тогда подтянутся текущие глобальные дефолты пользователя."""
    values = {f: getattr(payload, f) for f in DEFAULTS_FIELDS}

    # Пустой набор дефолтов в запросе -> берём текущие глобальные дефолты
    if all(v is None for v in values.values()):
        glob = (
            await db.execute(
                select(ExportDefault).where(
                    ExportDefault.user_id == current_user.id,
                    ExportDefault.category_name.is_(None),
                )
            )
        ).scalar_one_or_none()
        if glob:
            for f in DEFAULTS_FIELDS:
                val = getattr(glob, f)
                if f == "price_default" and val is not None:
                    val = float(val)
                values[f] = val
        else:
            raise HTTPException(
                status_code=400,
                detail="Не переданы дефолты и глобальные дефолты не заданы — "
                "заполните «Дефолты» или передайте значения в запросе",
            )

    row = (
        await db.execute(
            select(MigrationProfile).where(
                MigrationProfile.user_id == current_user.id,
                MigrationProfile.name == payload.name,
            )
        )
    ).scalar_one_or_none()

    created = row is None
    if row is None:
        # Лимит количества профилей (защита от свалки)
        count = len(
            (
                await db.execute(
                    select(MigrationProfile.id).where(MigrationProfile.user_id == current_user.id)
                )
            ).scalars().all()
        )
        if count >= MAX_PROFILES_PER_USER:
            raise HTTPException(
                status_code=400,
                detail=f"Максимум {MAX_PROFILES_PER_USER} профилей — удалите лишние",
            )
        row = MigrationProfile(user_id=current_user.id, name=payload.name)
        db.add(row)

    row.platform = payload.platform
    for f, v in values.items():
        setattr(row, f, v)

    await db.commit()
    await db.refresh(row)
    logger.info(
        f"⚙️ profile {'created' if created else 'updated'}: user={current_user.id} "
        f"name={row.name} platform={row.platform}"
    )
    return {"success": True, "profile": _row_to_dict(row), "created": created}


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    row = (
        await db.execute(
            select(MigrationProfile).where(
                MigrationProfile.id == profile_id,
                MigrationProfile.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Профиль не найден")

    await db.delete(row)
    await db.commit()
    return {"success": True}


@router.post("/{profile_id}/apply")
async def apply_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Применить профиль: сохранить его дефолты как ГЛОБАЛЬНЫЕ дефолты пользователя.
    Дальше миграция/«Заполнить пропуски» дозаполнит пустые поля по ним.
    Возвращает площадку профиля — фронт сразу подставляет её в окно миграции.
    """
    profile = (
        await db.execute(
            select(MigrationProfile).where(
                MigrationProfile.id == profile_id,
                MigrationProfile.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Профиль не найден")

    glob = (
        await db.execute(
            select(ExportDefault).where(
                ExportDefault.user_id == current_user.id,
                ExportDefault.category_name.is_(None),
            )
        )
    ).scalar_one_or_none()
    if glob is None:
        glob = ExportDefault(user_id=current_user.id, category_name=None)
        db.add(glob)

    for f in DEFAULTS_FIELDS:
        setattr(glob, f, getattr(profile, f))

    await db.commit()
    logger.info(f"⚙️ profile applied: user={current_user.id} profile={profile.name}")
    return {
        "success": True,
        "platform": profile.platform,
        "defaults": {
            f: (
                float(getattr(profile, f))
                if f == "price_default" and getattr(profile, f) is not None
                else getattr(profile, f)
            )
            for f in DEFAULTS_FIELDS
        },
    }
