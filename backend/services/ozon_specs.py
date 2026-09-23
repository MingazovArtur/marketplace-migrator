"""
Загрузчик спецификаций категорий Ozon через официальный Seller API.

Эндпоинты:
- POST /v1/description-category/tree             → дерево категорий (с type_id у листьев)
- POST /v1/description-category/attribute        → атрибуты категории со словарями
- POST /v1/description-category/attribute/values → значения словаря (пагинация по last_value_id)

Документация: https://docs.ozon.ru/api/seller/
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

OZON_API_BASE = "https://api-seller.ozon.ru"

# Пауза между запросами категорий — бережём rate-limit Ozon
CATEGORY_DELAY = 0.1
# Максимальное количество страниц словаря (защита от бесконечного цикла)
MAX_DICT_PAGES = 20
_DICT_CACHE: dict = {}


def _ozon_headers(api_key: str, client_id: str) -> dict:
    """Ozon требует Client-Id + Api-Key (не Bearer!)."""
    return {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json",
    }


def _parse_ozon_key(raw_key: str) -> tuple[str, str]:
    """
    Ключ Ozon вводится как 'CLIENT_ID:API_KEY'.
    CLIENT_ID — число (например 1234567), API_KEY — UUID.
    """
    raw_key = (raw_key or "").strip()
    if ":" not in raw_key:
        raise ValueError(
            "Формат ключа Ozon: 'CLIENT_ID:API_KEY', например "
            "'1234567:e30b97e3-997e-4574-8ddf-56466bcd20b8'. "
            "Оба значения — в кабинете Ozon: Настройки → API-ключи."
        )
    client_id, api_key = raw_key.split(":", 1)
    client_id = client_id.strip()
    api_key = api_key.strip()

    if not client_id.isdigit():
        raise ValueError(
            f"Client ID должен быть ЧИСЛОМ, получено: '{client_id}'. "
            "Не пишите слово 'client_id' — укажите числовой ID из кабинета Ozon "
            "(Настройки → API-ключи), например '1234567:e30b97e3-...'"
        )
    if not api_key:
        raise ValueError("После двоеточия пустой API-ключ.")
    return client_id, api_key

# ==================== Retry-обёртка ====================

async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    json_body: Optional[dict] = None,
    max_retries: int = 3,
) -> httpx.Response:
    """
    HTTP-запрос с retry на 429 (rate-limit) и 5xx (server error).
    Экспоненциальная задержка: 1s → 2s → 4s.
    """
    delay = 1.0
    last_exc = None
    for attempt in range(max_retries):
        try:
            if method == "POST":
                resp = await client.post(url, headers=headers, json=json_body or {})
            else:
                resp = await client.get(url, headers=headers)

            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning(
                    f"Ozon {resp.status_code} on {url} (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(delay)
                delay *= 2
                continue

            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 or e.response.status_code >= 500:
                last_exc = e
                await asyncio.sleep(delay)
                delay *= 2
                continue
            raise
    raise last_exc or httpx.HTTPError(f"Max retries exceeded for {url}")


# ==================== Дерево категорий ====================

async def fetch_ozon_category_tree(
    client: httpx.AsyncClient, client_id: str, api_key: str
) -> list[dict]:
    """
    Плоский список ЛИСТЬЕВ дерева категорий Ozon.

    ✅ Структура ответа Ozon:
      - Промежуточные узлы: description_category_id + category_name + children
      - Листья: type_id + type_name + children: [] (БЕЗ description_category_id)

    Для запроса атрибутов нужна пара: description_category_id (родителя) + type_id (листа).
    """
    headers = _ozon_headers(api_key, client_id)
    resp = await _request_with_retry(
        client, "POST",
        f"{OZON_API_BASE}/v1/description-category/tree",
        headers=headers,
        json_body={"language": "DEFAULT"},
    )
    data = resp.json()
    result = data.get("result") or []

    # ✅ Диагностика: сырой образец структуры
    if result:
        logger.info(
            f"Ozon tree raw sample: {json.dumps(result[0], ensure_ascii=False)[:1500]}"
        )
    else:
        logger.warning(f"Ozon tree: пустой result. Ключи ответа: {list(data.keys())}")

    leaves = []
    stats = {"total": 0, "leaves": 0, "skipped": 0}

    def walk(nodes, parent_cat_id=None, parent_cat_name=None):
        for node in nodes:
            stats["total"] += 1
            children = node.get("children") or []

            # Промежуточный узел: есть description_category_id
            own_cat_id = node.get("description_category_id")
            own_cat_name = node.get("category_name")

            # Лист: есть type_id и type_name
            type_id = node.get("type_id")
            type_name = node.get("type_name")

            if children:
                # Это промежуточный узел — спускаемся в детей
                walk(
                    children,
                    parent_cat_id=own_cat_id or parent_cat_id,
                    parent_cat_name=own_cat_name or parent_cat_name,
                )
                continue

            # Это лист (children пустой)
            if not type_id or not type_name:
                stats["skipped"] += 1
                continue

            # Для атрибутов нужен description_category_id родителя
            cat_id = parent_cat_id
            cat_name = parent_cat_name

            if not cat_id:
                stats["skipped"] += 1
                continue

            leaves.append({
                "id": str(cat_id),  # description_category_id родителя
                "type_id": int(type_id),  # type_id листа
                "name": cat_name,
                "type_name": type_name,
                "parent_id": None,
                "is_leaf": True,
                "disabled": bool(node.get("disabled")),
            })
            stats["leaves"] += 1

    walk(result)

    logger.info(
        f"Ozon tree: total={stats['total']}, leaves={stats['leaves']}, skipped={stats['skipped']}"
    )

    # Отключаемые категории не грузим
    return [leaf for leaf in leaves if not leaf["disabled"]]


# ==================== Атрибуты категории ====================

async def fetch_ozon_attributes(
    client: httpx.AsyncClient,
    client_id: str,
    api_key: str,
    description_category_id: int,
    type_id: int = 0,
    only_required_dicts: bool = True,
) -> list[dict]:
    """Атрибуты категории. Словари грузим только для обязательных/множественных (экономия запросов)."""
    headers = _ozon_headers(api_key, client_id)
    resp = await _request_with_retry(
        client, "POST",
        f"{OZON_API_BASE}/v1/description-category/attribute",
        headers=headers,
        json_body={
            "description_category_id": description_category_id,
            "type_id": type_id,
            "language": "DEFAULT",
        },
    )
    data = resp.json()

    attributes = []
    for attr in data.get("result", []):
        dict_id = attr.get("dictionary_id") or 0
        is_required = bool(attr.get("is_required"))
        is_collection = bool(attr.get("is_collection") or attr.get("is_dependent"))

        dict_values = None
        if dict_id and (is_required or is_collection or not only_required_dicts):
            dict_values = await _fetch_dictionary(
                client, client_id, api_key,
                attribute_id=int(attr.get("id") or 0),
                description_category_id=description_category_id,
                type_id=type_id,
                dictionary_id=dict_id,
            )

        base_type = _map_ozon_type(attr.get("type", ""), dict_id)
        if base_type == "select" and is_collection:
            base_type = "multiselect"

        attributes.append({
            "id": str(attr.get("id")),
            "name": attr.get("name"),
            "type": base_type,
            "required": is_required,
            "group": _map_ozon_group(attr.get("group_id")),
            "values": dict_values,
            "case_sensitive": bool(attr.get("is_case_sensitive", True)),
            "separator": ";",
            "unit": attr.get("unit"),
            "allow_unit_in_value": False,
            "dictionary_id": dict_id,
        })

    return attributes


# ==================== Словари значений ====================

async def _fetch_dictionary(
    client: httpx.AsyncClient,
    client_id: str,
    api_key: str,
    attribute_id: int,
    description_category_id: int,
    type_id: int,
    dictionary_id: int,
    page_size: int = 5000,
) -> Optional[list[str]]:
    """
    Значения словаря атрибута.
    ✅ Актуальный контракт Ozon: attribute_id + description_category_id + type_id
       (dictionary_id больше не принимается как основной ключ).
    ✅ Кэш: один dictionary_id грузится один раз за прогон.
    """
    if dictionary_id in _DICT_CACHE:
        return _DICT_CACHE[dictionary_id]

    headers = _ozon_headers(api_key, client_id)
    all_values: list[str] = []
    last_value_id = 0

    try:
        for _page in range(MAX_DICT_PAGES):
            resp = await _request_with_retry(
                client, "POST",
                f"{OZON_API_BASE}/v1/description-category/attribute/values",
                headers=headers,
                json_body={
                    "attribute_id": attribute_id,
                    "description_category_id": description_category_id,
                    "type_id": type_id,
                    "language": "DEFAULT",
                    "last_value_id": last_value_id,
                    "limit": page_size,
                },
            )
            items = resp.json().get("result", []) or []
            if not items:
                break

            for item in items:
                v = item.get("value")
                if v is not None and v != "":
                    all_values.append(str(v))

            new_last = items[-1].get("id")
            if new_last is None or new_last == last_value_id:
                break
            last_value_id = new_last

            if len(items) < page_size:
                break
    except Exception as e:
        logger.warning(f"Failed to fetch dictionary {dictionary_id}: {e}")
        _DICT_CACHE[dictionary_id] = None
        return None

    values = all_values or None
    _DICT_CACHE[dictionary_id] = values
    return values


# ==================== Маппинг типов и групп ====================

def _map_ozon_type(ozon_type: str, dictionary_id: int) -> str:
    """
    Озон возвращает тип String для свободного текста и для словарей.
    Различаем по наличию dictionary_id.
    """
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


def _map_ozon_group(group_id: Optional[int]) -> str:
    """Эмпирические group_id из документации Ozon."""
    groups = {
        1: "common",       # одинаковые для всех вариантов
        2: "brand",        # бренд
        3: "variant",      # атрибуты вариантов (цвет, размер)
        4: "additional",   # дополнительные
        5: "fits_for",     # "для чего подходит"
    }
    return groups.get(group_id, "common")


# ==================== Оркестратор ====================

async def refresh_ozon_specs(
    user_id: int,
    raw_api_key: str,
    category_ids: Optional[list[str]] = None,
    progress_cb=None,
) -> dict:
    client_id, api_key = _parse_ozon_key(raw_api_key)
    _DICT_CACHE.clear()   # ✅ свежий кэш на прогон

    async with httpx.AsyncClient(timeout=60) as client:
        tree = await fetch_ozon_category_tree(client, client_id, api_key)
        tree = [n for n in tree if n.get("id") and n.get("type_id")]
        if category_ids:
            tree = [n for n in tree if n["id"] in category_ids]

        total = len(tree)
        logger.info(f"Ozon: will process {total} category-type pairs")
        if progress_cb:
            progress_cb({"status": "running", "fetched": 0, "errors": 0, "total": total})

        fetched = 0
        errors = []

        for i, node in enumerate(tree):
            try:
                attrs = await fetch_ozon_attributes(
                    client, client_id, api_key,
                    description_category_id=int(node["id"]),
                    type_id=int(node.get("type_id") or 0),
                )
                spec_content = {
                    "sheets": ["Шаблон Поставщика", "Документация PDF", "Озон.Видео", "Озон.Видеообложка"],
                    "required_fields": [a["name"] for a in attrs if a["required"]],
                    "attributes": attrs,
                    "validation_rules": _build_validation_rules(attrs),
                    "special_requirements": _build_special_requirements(),
                }
                _upsert_spec(
                    user_id=user_id,
                    platform="ozon",
                    category_id=f"{node['id']}_{node['type_id']}",
                    category_name=f"{node['name']} / {node['type_name']}",
                    parent_category_id=node["parent_id"],
                    spec=spec_content,
                )
                fetched += 1
            except Exception as e:
                errors.append({"category_id": node["id"], "type_id": node.get("type_id"), "error": str(e)})
                logger.warning(f"Failed attrs {node['id']}/{node.get('type_id')}: {e}")

            if progress_cb and i % 5 == 0:
                progress_cb({"status": "running", "fetched": fetched, "errors": len(errors), "total": total})

            await asyncio.sleep(CATEGORY_DELAY)

    logger.info(f"Ozon refresh complete: fetched={fetched}, errors={len(errors)}")
    return {"platform": "ozon", "fetched": fetched, "errors": len(errors), "error_details": errors[:20]}

# ==================== Валидационные правила ====================

def _build_validation_rules(attrs: list[dict]) -> dict:
    rules = {
        "barcode": {"pattern": "^[0-9]{8,14}$", "separator": ";"},
        "vat_rate": {"enum": ["none", "10", "22"]},
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
    """
    Специальные требования Ozon (из официальной документации seller-edu.ozon.ru).
    """
    return {
        "okpd_required_for_tags": [
            "одежда", "обувь", "шубы", "парфюмерия", "духи", "туалетная вода",
            "лекарства", "шины", "покрышки", "фотоаппараты", "лампы-вспышки",
            "товары лёгкой промышленности",
        ],
        "excisable_tags": [
            "сахаросодержащие напитки", "моторные масла", "безалкогольное пиво",
        ],
    }


# ==================== Persistence ====================

def _upsert_spec(
    user_id, platform, category_id, category_name, parent_category_id, spec
):
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
        version = hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest()[:12]

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