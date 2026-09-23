"""
Загрузчик спецификаций Wildberries через Content API v2.

Эндпоинты:
- GET  /content/v2/object/parent/all            → все предметы (subjects)
- POST /content/v2/object/characteristics/list  → характеристики предмета
- GET  /content/v2/directory/{directoryID}      → значения словаря

Авторизация: сырой токен в заголовке Authorization (без схемы).
Документация: https://dev.wildberries.ru/docs/openapi/item-management
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

import httpx

from database.models import PlatformCategorySpec
from database.session import SessionLocal

logger = logging.getLogger(__name__)

WB_API_BASE = "https://content-api.wildberries.ru"

# Пауза между запросами характеристик — бережём rate-limit WB
WB_REQUEST_DELAY = 0.2


def _wb_headers(token: str) -> dict:
    """WB принимает сырой токен без схемы Bearer/OAuth."""
    return {
        "Authorization": token,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


# ========== Предметы (категории WB) ==========

async def fetch_wb_subjects(client: httpx.AsyncClient, token: str) -> list[dict]:
    """Список всех предметов Wildberries."""
    resp = await client.get(
        f"{WB_API_BASE}/content/v2/object/parent/all",
        headers=_wb_headers(token),
    )
    resp.raise_for_status()
    data = resp.json()

    items = data.get("data") if isinstance(data, dict) else data
    items = items or []

    out = []
    for s in items:
        out.append({
            "id": str(s.get("objectID") or s.get("id")),
            "name": s.get("object") or s.get("name") or str(s.get("objectID")),
            "parent_id": str(s.get("parentID")) if s.get("parentID") else None,
        })
    return out


# ========== Характеристики предмета ==========

async def fetch_wb_characteristics(client: httpx.AsyncClient, token: str, object_id: str) -> list[dict]:
    """Характеристики конкретного предмета."""
    resp = await client.post(
        f"{WB_API_BASE}/content/v2/object/characteristics/list",
        headers=_wb_headers(token),
        json={"objectID": int(object_id)},
    )
    resp.raise_for_status()
    data = resp.json()

    items = data.get("data") if isinstance(data, dict) else data
    items = items or []

    attributes = []
    for ch in items:
        directory_id = ch.get("directoryID") or 0
        max_count = ch.get("maxCount") or 1

        values = None
        if directory_id:
            values = await fetch_wb_directory(client, token, directory_id)

        base_type = _map_wb_type(ch, directory_id)
        if base_type == "select" and max_count and max_count > 1:
            base_type = "multiselect"

        attributes.append({
            "id": str(ch.get("id")),
            "name": ch.get("name"),
            "type": base_type,
            "required": bool(ch.get("required")),
            "group": _map_wb_group(ch),
            "values": values,
            "case_sensitive": True,
            "separator": ";",
            "unit": ch.get("unit") or None,
            "allow_unit_in_value": False,
            "max_count": max_count,
        })

    return attributes


async def fetch_wb_directory(client: httpx.AsyncClient, token: str, directory_id: int, limit: int = 1000) -> Optional[list[str]]:
    """Значения словаря WB (цвета, размеры и т.д.)."""
    try:
        resp = await client.get(
            f"{WB_API_BASE}/content/v2/directory/{directory_id}",
            headers=_wb_headers(token),
            params={"limit": limit},
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data") if isinstance(data, dict) else data
            items = items or []
            return [i.get("value") or i.get("name") for i in items if i.get("value") or i.get("name")]
    except Exception as e:
        logger.warning(f"WB: не удалось получить словарь {directory_id}: {e}")
    return None


def _map_wb_type(ch: dict, directory_id: int) -> str:
    """Эвристика типов WB: словарь → select, единицы измерения → number, иначе text."""
    raw = (ch.get("type") or ch.get("valueType") or "").lower()
    if raw in ("number", "integer", "decimal", "float"):
        return "number"
    if raw in ("boolean", "bool"):
        return "select"
    if directory_id:
        return "select"
    unit = (ch.get("unit") or "").strip()
    if unit:
        return "number"
    return "text"


def _map_wb_group(ch: dict) -> str:
    name = (ch.get("name") or "").strip().lower()
    if name in ("бренд", "brand"):
        return "brand"
    return "common"


# ========== Оркестратор ==========

async def refresh_wildberries_specs(
    user_id: int,
    token: str,
    category_ids: Optional[list[str]] = None,
) -> dict:
    """Подтягивает предметы + характеристики, сохраняет как PlatformCategorySpec."""
    async with httpx.AsyncClient(timeout=60) as client:
        subjects = await fetch_wb_subjects(client, token)

        if category_ids:
            subjects = [s for s in subjects if s["id"] in category_ids]

        fetched = 0
        errors = []

        for s in subjects:
            try:
                attrs = await fetch_wb_characteristics(client, token, s["id"])

                spec_content = {
                    # WB Excel-выгрузка из редактора карточек — один лист
                    "sheets": ["Товары"],
                    "required_fields": [a["name"] for a in attrs if a["required"]],
                    "attributes": attrs,
                    "validation_rules": _build_validation_rules(attrs),
                    "special_requirements": _build_special_requirements(),
                }

                _upsert_spec(
                    user_id=user_id,
                    platform="wildberries",
                    category_id=s["id"],
                    category_name=s["name"],
                    parent_category_id=s["parent_id"],
                    spec=spec_content,
                )
                fetched += 1
            except Exception as e:
                errors.append({"category_id": s["id"], "error": str(e)})
                logger.warning(f"WB: ошибка загрузки характеристик предмета {s['id']}: {e}")

            await asyncio.sleep(WB_REQUEST_DELAY)   # бережём rate-limit

    return {
        "platform": "wildberries",
        "fetched": fetched,
        "errors": len(errors),
        "error_details": errors[:20],
    }


def _build_validation_rules(attrs: list[dict]) -> dict:
    rules = {
        "price": {"min": 0.01},
        "units_per_item": {"min": 1, "type": "integer"},
    }
    for attr in attrs:
        if attr["values"]:
            rules[attr["id"]] = {
                "enum": attr["values"],
                "case_sensitive": attr["case_sensitive"],
                "separator": attr["separator"] if attr["type"] == "multiselect" else None,
            }
        if attr.get("max_count"):
            rules.setdefault(attr["id"], {})["max_values"] = attr["max_count"]
    return rules


def _build_special_requirements() -> dict:
    return {
        "okpd_required_for_tags": [],
        "excisable_tags": [],
    }


def _upsert_spec(user_id, platform, category_id, category_name, parent_category_id, spec):
    db = SessionLocal()
    try:
        existing = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.user_id == user_id,
                PlatformCategorySpec.platform == platform,
                PlatformCategorySpec.category_id == category_id,
            )
            .first()
        )
        version = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]

        if existing:
            existing.category_name = category_name
            existing.parent_category_id = parent_category_id
            existing.spec = spec
            existing.version = version
            existing.fetched_at = datetime.utcnow()
        else:
            db.add(PlatformCategorySpec(
                user_id=user_id,
                platform=platform,
                category_id=category_id,
                category_name=category_name,
                parent_category_id=parent_category_id,
                spec=spec,
                version=version,
            ))
        db.commit()
    finally:
        db.close()