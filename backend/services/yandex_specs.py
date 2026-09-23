"""
Загрузчик спецификаций категорий Яндекс Маркета через официальный Partner API.

Эндпоинты (Content API):
- GET /businesses/{businessId}/categories
- GET /businesses/{businessId}/categories/{categoryId}/versions
- GET /businesses/{businessId}/categories/{categoryId}/versions/{version}/parameters
- GET /businesses/{businessId}/categories/{categoryId}/versions/{version}/parameters/{parameterId}/variants

Документация: https://yandex.ru/dev/market/partner-api/
OpenAPI-спека: https://github.com/yandex-market/yandex-market-partner-api
"""
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

import httpx

from database.models import PlatformCategorySpec
from database.session import SessionLocal

logger = logging.getLogger(__name__)

YANDEX_API_BASE = "https://api.partner.market.yandex.ru"


def _ym_headers(token: str) -> dict:
    """Яндекс использует схему 'OAuth', а не 'Bearer'."""
    return {
        "Authorization": f"OAuth {token}",
        "Accept": "application/json",
    }


# ========== Категории ==========

async def fetch_yandex_categories(client: httpx.AsyncClient, token: str, business_id: str) -> list[dict]:
    """Список категорий кабинета (с пагинацией)."""
    out = []
    page = 1
    while page <= 20:
        resp = await client.get(
            f"{YANDEX_API_BASE}/businesses/{business_id}/categories",
            headers=_ym_headers(token),
            params={"page": page, "page_size": 100},
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result") or {}
        if isinstance(result, list):
            cats = result
        else:
            cats = result.get("categories") or result.get("items") or []

        for c in cats:
            out.append({
                "id": str(c.get("id")),
                "name": c.get("name") or c.get("title") or str(c.get("id")),
                "parent_id": str(c.get("parentId")) if c.get("parentId") else None,
                "version": c.get("version"),
            })

        # пагинация: если категорий меньше страницы — выходим
        if len(cats) < 100:
            break
        page += 1

    return out


async def fetch_yandex_category_version(
    client: httpx.AsyncClient, token: str, business_id: str, category_id: str, fallback: Optional[int] = None
) -> int:
    """Определяем актуальную версию категории (нужна для запроса параметров)."""
    if fallback:
        return fallback
    try:
        resp = await client.get(
            f"{YANDEX_API_BASE}/businesses/{business_id}/categories/{category_id}/versions",
            headers=_ym_headers(token),
        )
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("result") or {}
            versions = result.get("versions") if isinstance(result, dict) else result
            versions = versions or []
            nums = [v.get("version") if isinstance(v, dict) else v for v in versions]
            nums = [n for n in nums if isinstance(n, int)]
            if nums:
                return max(nums)
    except Exception as e:
        logger.warning(f"Yandex: не удалось получить версии категории {category_id}: {e}")
    return 1


# ========== Атрибуты ==========

async def fetch_yandex_parameters(
    client: httpx.AsyncClient, token: str, business_id: str, category_id: str, version: int
) -> list[dict]:
    """Параметры (характеристики) категории со словарями значений."""
    resp = await client.get(
        f"{YANDEX_API_BASE}/businesses/{business_id}/categories/{category_id}/versions/{version}/parameters",
        headers=_ym_headers(token),
    )
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result") or {}
    params = result.get("parameters") or result.get("items") or []
    if isinstance(result, list):
        params = result

    attributes = []
    for p in params:
        is_collection = bool(p.get("collection") or p.get("isCollection") or p.get("multiple"))
        variants = p.get("variants") or p.get("values") or []
        values = None
        if variants:
            values = [v.get("value") if isinstance(v, dict) else v for v in variants]

        base_type = _map_yandex_type(p.get("type"))
        if base_type == "select" and is_collection:
            base_type = "multiselect"

        attributes.append({
            "id": str(p.get("id")),
            "name": p.get("name"),
            "type": base_type,
            "required": bool(p.get("required") or p.get("isRequired")),
            "group": _map_yandex_group(p),
            "values": values,
            "case_sensitive": True,
            "separator": ";",
            "unit": p.get("unit"),
            "allow_unit_in_value": False,
        })

    return attributes


def _map_yandex_type(t: Optional[str]) -> str:
    t = (t or "").upper()
    if t in ("NUMBER", "INTEGER", "DECIMAL", "FLOAT"):
        return "number"
    if t in ("ENUM", "BOOLEAN"):
        return "select"
    return "text"


def _map_yandex_group(p: dict) -> str:
    name = (p.get("name") or "").strip().lower()
    if name in ("бренд", "brand"):
        return "brand"
    group = (p.get("group") or p.get("groupName") or "").lower()
    if "вариант" in group or "variant" in group:
        return "variant"
    if "дополнительн" in group or "additional" in group:
        return "additional"
    return "common"


# ========== Оркестратор ==========

async def refresh_yandex_specs(
    user_id: int,
    token: str,
    business_id: str,
    category_ids: Optional[list[str]] = None,
) -> dict:
    """Подтягивает категории + параметры, сохраняет как PlatformCategorySpec."""
    async with httpx.AsyncClient(timeout=60) as client:
        cats = await fetch_yandex_categories(client, token, business_id)

        if category_ids:
            cats = [c for c in cats if c["id"] in category_ids]

        fetched = 0
        errors = []

        for c in cats:
            try:
                version = await fetch_yandex_category_version(
                    client, token, business_id, c["id"], c.get("version")
                )
                attrs = await fetch_yandex_parameters(client, token, business_id, c["id"], version)

                spec_content = {
                    "sheets": ["Список товаров", "Инструкция", "Описание полей"],
                    "required_fields": [a["name"] for a in attrs if a["required"]],
                    "attributes": attrs,
                    "validation_rules": _build_validation_rules(attrs),
                    "special_requirements": _build_special_requirements(),
                }

                _upsert_spec(
                    user_id=user_id,
                    platform="yandex",
                    category_id=c["id"],
                    category_name=c["name"],
                    parent_category_id=c["parent_id"],
                    spec=spec_content,
                )
                fetched += 1
            except Exception as e:
                errors.append({"category_id": c["id"], "error": str(e)})
                logger.warning(f"Yandex: ошибка загрузки параметров категории {c['id']}: {e}")

    return {
        "platform": "yandex",
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
    return rules


def _build_special_requirements() -> dict:
    return {
        "okpd_required_for_tags": [],   # у Яндекса маркировка контролируется иначе
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