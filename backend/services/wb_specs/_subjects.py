"""Предметы (категории) Wildberries — GET /content/v2/object/parent/all[cite: 12]."""

import httpx

from services.wb_specs._http import WB_API_BASE, _wb_headers


async def fetch_wb_subjects(client: httpx.AsyncClient, token: str) -> list[dict]:
    """Список всех предметов Wildberries[cite: 12]."""
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
        out.append(
            {
                "id": str(s.get("objectID") or s.get("id")),
                "name": s.get("object") or s.get("name") or str(s.get("objectID")),
                "parent_id": str(s.get("parentID")) if s.get("parentID") else None,
            }
        )
    return out
