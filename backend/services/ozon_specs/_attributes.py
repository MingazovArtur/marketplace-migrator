"""Атрибуты категории Ozon: словари значений, маппинг типов, сборка спека.

Константы словарей (MAX_VALUES_PER_ATTR/MAX_DICT_PAGES) и базовые обязательные
поля живут здесь. Вынесено без изменений из монолита services/ozon_specs.py (Р8).
"""

import asyncio
import logging

import httpx

from services.ozon_specs._http import _post

logger = logging.getLogger(__name__)

MAX_VALUES_PER_ATTR = 500  # потолок значений словаря (было 1000)
MAX_DICT_PAGES = 3  # максимум страниц на словарь (было 5)

BASE_REQUIRED_FIELDS = [
    "Артикул",
    "Предельная цена без акций",
    "НДС, %",
    "Ссылка на главное фото",
]


# =====================================================================
# Словари значений (с лимитом и параллельно)
# =====================================================================


async def _fetch_values(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    headers: dict,
    description_category_id: int,
    type_id: int,
    attribute_id: int,
) -> list[str]:
    """Значения одного словаря. Лимит MAX_VALUES_PER_ATTR."""
    all_values: list[str] = []
    last_value_id = 0

    try:
        for _page in range(MAX_DICT_PAGES):
            data = await _post(
                client,
                sem,
                "/v1/description-category/attribute/values",
                {
                    "attribute_id": attribute_id,
                    "description_category_id": description_category_id,
                    "type_id": type_id,
                    "language": "DEFAULT",
                    "last_value_id": last_value_id,
                    "limit": MAX_VALUES_PER_ATTR,
                },
                headers,
            )
            items = data.get("result", []) or []
            if not items:
                break

            for item in items:
                v = item.get("value")
                if v is not None and v != "":
                    all_values.append(str(v))
                if len(all_values) >= MAX_VALUES_PER_ATTR:
                    return all_values

            new_last = items[-1].get("id")
            if new_last is None or new_last == last_value_id:
                break
            last_value_id = new_last

            if len(items) < MAX_VALUES_PER_ATTR:
                break
    except Exception as e:
        logger.warning(f"Словарь не загружен {description_category_id}/{attribute_id}: {e}")
        return []

    return all_values


# =====================================================================
# Маппинг атрибутов Ozon → наша схема CategoryAttributeSpec
# =====================================================================


def _map_ozon_type(ozon_type: str, dictionary_id: int) -> str:
    ozon_type = (ozon_type or "").strip()
    if ozon_type in ("Integer", "Decimal", "Float", "Number"):
        return "number"
    if ozon_type in ("Boolean", "Bool"):
        return "select"
    if ozon_type in ("URL",):
        return "text"
    if dictionary_id:
        return "select"
    return "text"


def _map_ozon_group(group_id: int | None) -> str:
    groups = {
        1: "common",
        2: "brand",
        3: "variant",
        4: "additional",
        5: "fits_for",
    }
    return groups.get(group_id, "common")


def _map_attribute(attr: dict, values: list[str] | None) -> dict:
    """Приводит атрибут Ozon к нашей схеме CategoryAttributeSpec."""
    ozon_type = attr.get("type") or ""
    is_collection = bool(attr.get("is_collection") or attr.get("is_dependent"))
    dict_id = attr.get("dictionary_id") or 0

    base_type = _map_ozon_type(ozon_type, dict_id)
    if base_type == "select" and is_collection:
        base_type = "multiselect"

    return {
        "id": str(attr.get("id")),
        "name": attr.get("name") or "",
        "type": base_type,
        "required": bool(attr.get("is_required")),
        "group": _map_ozon_group(attr.get("group_id")),
        "values": values,
        "case_sensitive": bool(attr.get("is_case_sensitive", True)),
        "separator": "; " if is_collection else ";",
        "unit": attr.get("unit"),
        "allow_unit_in_value": base_type == "number",
        "dictionary_id": dict_id,
    }


# =====================================================================
# Валидационные правила
# =====================================================================


def _build_validation_rules(attrs: list[dict]) -> dict:
    rules = {
        "barcode": {"pattern": "^[0-9]{8,14}$", "separator": ";"},
        "vat_rate": {"enum": ["none", "10", "22"]},
        "price": {"min": 0.01},
        "units_per_item": {"min": 1, "type": "integer"},
    }
    for attr in attrs:
        if attr.get("values"):
            rules[attr["id"]] = {
                "enum": attr["values"],
                "case_sensitive": attr.get("case_sensitive", True),
                "separator": attr.get("separator") if attr.get("type") == "multiselect" else None,
            }
    return rules


def _build_special_requirements() -> dict:
    """Специальные требования Ozon (из официальной документации seller-edu.ozon.ru)."""
    return {
        "okpd_required_for_tags": [
            "одежда",
            "обувь",
            "шубы",
            "парфюмерия",
            "духи",
            "туалетная вода",
            "лекарства",
            "шины",
            "покрышки",
            "фотоаппараты",
            "лампы-вспышки",
            "товары лёгкой промышленности",
        ],
        "excisable_tags": [
            "сахаросодержащие напитки",
            "моторные масла",
            "безалкогольное пиво",
        ],
    }


# =====================================================================
# Сборка спека одной категории (атрибуты + параллельные словари)
# =====================================================================


async def _build_spec(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    headers: dict,
    leaf: dict,
) -> dict:
    """
    Собирает полную спеку одной категории:
    1) получает атрибуты (1 запрос)
    2) для атрибутов со словарями параллельно грузит значения (N запросов одновременно)
    3) формирует spec-объект
    """
    desc_id = int(leaf["id"])
    type_id = int(leaf.get("type_id") or 0)

    # 1) Атрибуты категории
    data = await _post(
        client,
        sem,
        "/v1/description-category/attribute",
        {
            "description_category_id": desc_id,
            "type_id": type_id,
            "language": "DEFAULT",
        },
        headers,
    )
    attrs = data.get("result") or []

    mapped = []
    dict_tasks = []  # [(индекс, coroutine)]

    for i, a in enumerate(attrs):
        dict_id = a.get("dictionary_id") or 0
        item = _map_attribute(a, None)
        mapped.append(item)

        if dict_id:
            dict_tasks.append(
                (
                    i,
                    _fetch_values(client, sem, headers, desc_id, type_id, int(a.get("id") or 0)),
                )
            )

    # 2) Параллельно грузим все словари
    if dict_tasks:
        results = await asyncio.gather(
            *(coro for _, coro in dict_tasks),
            return_exceptions=True,
        )
        for (idx, _), res in zip(dict_tasks, results, strict=True):
            if isinstance(res, Exception):
                logger.warning(f"Словарь не загружен {desc_id}/{mapped[idx]['id']}: {res}")
                mapped[idx]["values"] = []
            else:
                mapped[idx]["values"] = res

    # 3) Формируем spec
    return {
        "sheets": ["Шаблон Поставщика", "Документация PDF", "Озон.Видео", "Озон.Видеообложка"],
        "required_fields": BASE_REQUIRED_FIELDS + [a["name"] for a in mapped if a["required"]],
        "attributes": mapped,
        "validation_rules": _build_validation_rules(mapped),
        "special_requirements": _build_special_requirements(),
    }
