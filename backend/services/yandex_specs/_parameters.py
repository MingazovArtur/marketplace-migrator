"""Характеристики листовой категории Яндекс Маркета и правила валидации."""

import asyncio

import httpx

from services.yandex_specs._http import _post_ym

MAX_VALUES_PER_ATTR = 500

# Базовые обязательные колонки официального шаблона Яндекс Маркета
YM_BASE_REQUIRED_FIELDS = [
    "Ваш SKU",
    "Название товара",
    "Ссылка на изображение",
    "Описание товара",
    "Категория на Маркете",
    "Бренд",
    "Штрихкод",
    "Вес, кг",
    "Длина, см",
    "Ширина, см",
    "Высота, см",
    "Цена",
    "ТН ВЭД",
]


def _map_yandex_type(param_type: str | None, has_values: bool, multivalue: bool) -> str:
    t = (param_type or "").upper()
    if t in ("NUMERIC", "NUMBER", "INTEGER", "DECIMAL", "FLOAT"):
        return "number"
    if t in ("ENUM", "BOOLEAN") or has_values:
        return "multiselect" if multivalue else "select"
    return "text"


def _map_yandex_group(name: str) -> str:
    low = (name or "").strip().lower()
    if low in ("бренд", "brand", "вендор", "производитель"):
        return "brand"
    if any(k in low for k in ("цвет", "размер", "объем", "вес", "рост")):
        return "variant"
    return "common"


async def fetch_yandex_category_parameters(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    headers: dict,
    category_id: str,
) -> list[dict]:
    """Получает характеристики конкретной листовой категории Яндекс Маркета."""
    data = await _post_ym(
        client,
        sem,
        f"/category/{category_id}/parameters",
        {},
        headers,
    )
    result = data.get("result") or {}
    params = result.get("parameters") or []

    attributes: list[dict] = []
    for p in params:
        p_id = p.get("id")
        p_name = (p.get("name") or "").strip()
        if not p_id or not p_name:
            continue

        multivalue = bool(p.get("multivalue") or p.get("collection"))
        raw_values = p.get("values") or p.get("variants") or p.get("valueRestrictions") or []
        values: list[str] | None = None
        if isinstance(raw_values, list) and raw_values:
            extracted = []
            for v in raw_values[:MAX_VALUES_PER_ATTR]:
                val_str = v.get("value") if isinstance(v, dict) else str(v)
                if val_str:
                    extracted.append(str(val_str))
            if extracted:
                values = extracted

        unit_info = p.get("unit")
        unit_name = None
        if isinstance(unit_info, dict):
            unit_name = unit_info.get("fullName") or unit_info.get("name")
        elif isinstance(unit_info, str):
            unit_name = unit_info

        attr_type = _map_yandex_type(p.get("type"), bool(values), multivalue)

        attributes.append(
            {
                "id": str(p_id),
                "name": p_name,
                "type": attr_type,
                "required": bool(p.get("required") or p.get("mandatory")),
                "group": _map_yandex_group(p_name),
                "values": values,
                "case_sensitive": False,
                "separator": ";",
                "unit": unit_name,
                "allow_unit_in_value": True,
                "description": (p.get("description") or "")[:500],
            }
        )

    return attributes


def _build_validation_rules(attrs: list[dict]) -> dict:
    rules = {
        "price": {"min": 0.01},
        "units_per_item": {"min": 1, "type": "integer"},
    }
    for attr in attrs:
        if attr.get("values"):
            rules[attr["id"]] = {
                "enum": attr["values"],
                "case_sensitive": attr.get("case_sensitive", False),
                "separator": attr.get("separator") if attr.get("type") == "multiselect" else None,
            }
    return rules
