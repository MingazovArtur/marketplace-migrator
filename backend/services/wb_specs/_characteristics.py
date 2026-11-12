"""Характеристики предмета Wildberries, словари значений, правила валидации[cite: 12]."""

import logging

import httpx

from services.wb_specs._http import WB_API_BASE, _wb_headers

logger = logging.getLogger(__name__)


async def fetch_wb_characteristics(
    client: httpx.AsyncClient, token: str, object_id: str
) -> list[dict]:
    """Характеристики конкретного предмета[cite: 12]."""
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

        attributes.append(
            {
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
            }
        )

    return attributes


async def fetch_wb_directory(
    client: httpx.AsyncClient, token: str, directory_id: int, limit: int = 1000
) -> list[str] | None:
    """Значения словаря WB (цвета, размеры и т.д.)[cite: 12]."""
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
            return [
                i.get("value") or i.get("name") for i in items if i.get("value") or i.get("name")
            ]
    except Exception as e:
        logger.warning(f"WB: не удалось получить словарь {directory_id}: {e}")
    return None


def _map_wb_type(ch: dict, directory_id: int) -> str:
    """Эвристика типов WB: словарь → select, единицы измерения → number, иначе text[cite: 12]."""
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
