"""
Загрузчик спецификаций категорий Ozon через официальный Seller API.

v3 — ОПТИМИЗАЦИЯ ПАМЯТИ:
  - CONCURRENCY снижен с 15 до 5 (меньше одновременных запросов)
  - DB_CHUNK снижен с 200 до 50 (чаще коммитим, меньше буфер)
  - MAX_VALUES_PER_ATTR снижен с 1000 до 500 (словари меньше)
  - MAX_DICT_PAGES снижен с 5 до 3
  - Явный вызов gc.collect() после каждого чанка
  - Очистка буферов и кэшей после commit

Ожидаемое время загрузки: 20-40 минут (медленнее, но стабильно на 2GB RAM)

Эндпоинты Ozon:
- POST /v1/description-category/tree             → дерево категорий
- POST /v1/description-category/attribute        → атрибуты категории
- POST /v1/description-category/attribute/values → значения словаря
"""
import asyncio
import gc
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional, Callable

import httpx

from database.models import PlatformCategorySpec
from database.session import SessionLocal

logger = logging.getLogger(__name__)

OZON_API_BASE = "https://api-seller.ozon.ru"

# =====================================================================
# Конфигурация параллелизма (ОПТИМИЗИРОВАНО ДЛЯ ПАМЯТИ)
# =====================================================================
CONCURRENCY = 5                   # одновременных запросов к API Ozon (было 15)
TIMEOUT = 60.0                    # таймаут одного запроса
MAX_VALUES_PER_ATTR = 500         # потолок значений словаря (было 1000)
MAX_DICT_PAGES = 3                # максимум страниц на словарь (было 5)
DB_CHUNK = 50                     # категорий на один commit (было 200)
PROGRESS_EVERY = 10               # частота вызова progress_cb (чаще для мониторинга)
MAX_RETRIES = 3                   # попыток на запрос

BASE_REQUIRED_FIELDS = [
    "Артикул",
    "Предельная цена без акций",
    "НДС, %",
    "Ссылка на главное фото",
]


# =====================================================================
# HTTP-слой с retry и семафором
# =====================================================================

def _ozon_headers(client_id: str, api_key: str) -> dict:
    """Ozon требует Client-Id + Api-Key (не Bearer!)."""
    return {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json",
    }


def _parse_ozon_key(raw_key: str) -> tuple[str, str]:
    """
    Ключ Ozon: 'CLIENT_ID:API_KEY'.
    CLIENT_ID — число, API_KEY — UUID.
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
            "Укажите числовой ID из кабинета Ozon (Настройки → API-ключи)."
        )
    if not api_key:
        raise ValueError("После двоеточия пустой API-ключ.")
    return client_id, api_key


async def _post(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    path: str,
    body: dict,
    headers: dict,
) -> dict:
    """POST с семафором (ограничение конкурентности) и retry на 429/5xx/транспорт."""
    async with sem:
        last_err = None
        delay = 1.0
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(f"{OZON_API_BASE}{path}", json=body, headers=headers)
                if resp.status_code == 429 or resp.status_code >= 500:
                    logger.warning(
                        f"⚠️ Ozon {resp.status_code} на {path} (попытка {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429,) or e.response.status_code >= 500:
                    last_err = e
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise
            except (httpx.TransportError, httpx.TimeoutException, OSError) as e:
                last_err = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                continue
        raise last_err or httpx.HTTPError(f"Max retries exceeded для {path}")


# =====================================================================
# Дерево категорий
# =====================================================================

async def fetch_ozon_category_tree(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    client_id: str,
    api_key: str,
) -> list[dict]:
    """
    Плоский список ЛИСТЬЕВ дерева категорий Ozon.
    Для атрибутов нужна пара: description_category_id (родителя) + type_id (листа).
    """
    headers = _ozon_headers(client_id, api_key)
    data = await _post(client, sem, "/v1/description-category/tree",
                       {"language": "DEFAULT"}, headers)
    result = data.get("result") or []

    leaves = []
    stats = {"total": 0, "leaves": 0, "skipped": 0}

    def walk(nodes, parent_cat_id=None, parent_cat_name=None):
        for node in nodes:
            stats["total"] += 1
            children = node.get("children") or []
            own_cat_id = node.get("description_category_id")
            own_cat_name = node.get("category_name")
            type_id = node.get("type_id")
            type_name = node.get("type_name")

            if children:
                walk(
                    children,
                    parent_cat_id=own_cat_id or parent_cat_id,
                    parent_cat_name=own_cat_name or parent_cat_name,
                )
                continue

            if not type_id or not type_name:
                stats["skipped"] += 1
                continue

            cat_id = parent_cat_id
            cat_name = parent_cat_name
            if not cat_id:
                stats["skipped"] += 1
                continue

            leaves.append({
                "id": str(cat_id),
                "type_id": int(type_id),
                "name": cat_name or "",
                "type_name": type_name or "",
                "parent_id": None,
                "disabled": bool(node.get("disabled")),
            })
            stats["leaves"] += 1

    walk(result)
    logger.info(
        f"🌳 Ozon tree: total={stats['total']}, leaves={stats['leaves']}, skipped={stats['skipped']}"
    )
    return [leaf for leaf in leaves if not leaf["disabled"]]


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
        for page in range(MAX_DICT_PAGES):
            data = await _post(
                client, sem,
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
# Сборка спека одной категории (атрибуты + параллельные словари)
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


def _map_ozon_group(group_id: Optional[int]) -> str:
    groups = {
        1: "common",
        2: "brand",
        3: "variant",
        4: "additional",
        5: "fits_for",
    }
    return groups.get(group_id, "common")


def _map_attribute(attr: dict, values: Optional[list[str]]) -> dict:
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
        client, sem,
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
            dict_tasks.append((
                i,
                _fetch_values(client, sem, headers, desc_id, type_id, int(a.get("id") or 0)),
            ))

    # 2) Параллельно грузим все словари
    if dict_tasks:
        results = await asyncio.gather(
            *(coro for _, coro in dict_tasks),
            return_exceptions=True,
        )
        for (idx, _), res in zip(dict_tasks, results):
            if isinstance(res, Exception):
                logger.warning(
                    f"Словарь не загружен {desc_id}/{mapped[idx]['id']}: {res}"
                )
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


# =====================================================================
# Пакетная запись в БД (ОПТИМИЗИРОВАНО)
# =====================================================================

def _flush_buffer(user_id: int, buffer: list[tuple[dict, dict]]) -> None:
    """Записывает буфер (leaf, spec) в БД одним commit-ом."""
    if not buffer:
        return

    db = SessionLocal()
    try:
        for leaf, spec in buffer:
            cid = f"{leaf['id']}_{leaf['type_id']}"
            cname = f"{leaf['name']} / {leaf['type_name']}"
            version = hashlib.sha256(
                json.dumps(spec, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()[:12]

            existing = (
                db.query(PlatformCategorySpec)
                .filter(
                    PlatformCategorySpec.platform == "ozon",
                    PlatformCategorySpec.category_id == cid,
                )
                .first()
            )

            if existing:
                existing.user_id = user_id
                existing.category_name = cname
                existing.parent_category_id = leaf.get("parent_id")
                existing.spec = spec
                existing.version = version
                existing.fetched_at = datetime.utcnow()
            else:
                db.add(PlatformCategorySpec(
                    user_id=user_id,
                    platform="ozon",
                    category_id=cid,
                    category_name=cname,
                    parent_category_id=leaf.get("parent_id"),
                    spec=spec,
                    version=version,
                ))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


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
            "одежда", "обувь", "шубы", "парфюмерия", "духи", "туалетная вода",
            "лекарства", "шины", "покрышки", "фотоаппараты", "лампы-вспышки",
            "товары лёгкой промышленности",
        ],
        "excisable_tags": [
            "сахаросодержащие напитки", "моторные масла", "безалкогольное пиво",
        ],
    }


# =====================================================================
# Главный оркестратор (вызывается из tasks.refresh_specs_task)
# =====================================================================

async def refresh_ozon_specs(
    user_id: int,
    raw_api_key: str,
    category_ids: Optional[list[str]] = None,
    progress_cb: Optional[Callable] = None,
    concurrency: int = CONCURRENCY,
) -> dict:
    """
    Фоновая загрузка спеков Ozon с оптимизацией памяти.
    Возвращает {"platform", "fetched", "errors", "error_details"}.
    """
    client_id, api_key = _parse_ozon_key(raw_api_key)
    headers = _ozon_headers(client_id, api_key)

    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(
        max_connections=concurrency + 5,
        max_keepalive_connections=concurrency,
    )

    fetched = 0
    errors = 0
    error_details = []
    done_count = 0
    buffer: list[tuple[dict, dict]] = []

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits) as client:
        # 1) Дерево категорий
        leaves = await fetch_ozon_category_tree(client, sem, client_id, api_key)
        leaves = [n for n in leaves if n.get("id") and n.get("type_id")]

        if category_ids:
            wanted = {str(c) for c in category_ids}
            leaves = [n for n in leaves if n["id"] in wanted]

        total = len(leaves)
        logger.info(f"🚀 Ozon: будет загружено {total} категорий (concurrency={concurrency})")

        if progress_cb:
            progress_cb({"total": total, "fetched": 0, "errors": 0})

        if total == 0:
            return {
                "platform": "ozon",
                "fetched": 0,
                "errors": 0,
                "error_details": [],
            }

        # 2) Обработка чанками: параллельно внутри, commit между чанками
        async def work(leaf: dict) -> None:
            nonlocal fetched, errors, done_count
            try:
                spec = await _build_spec(client, sem, headers, leaf)
                buffer.append((leaf, spec))
                fetched += 1
            except Exception as e:
                errors += 1
                if len(error_details) < 50:
                    error_details.append({
                        "category_id": leaf.get("id"),
                        "type_id": leaf.get("type_id"),
                        "error": str(e)[:300],
                    })
            finally:
                done_count += 1
                if progress_cb and (done_count % PROGRESS_EVERY == 0 or done_count == total):
                    progress_cb({"total": total, "fetched": fetched, "errors": errors})

        for i in range(0, total, DB_CHUNK):
            chunk = leaves[i:i + DB_CHUNK]
            await asyncio.gather(*(work(leaf) for leaf in chunk))

            # Commit чанка в БД
            try:
                _flush_buffer(user_id, buffer)
            except Exception as e:
                logger.error(f"❌ Ошибка commit чанка {i // DB_CHUNK}: {e}")
                errors += len(buffer)
                for leaf, _ in buffer:
                    if len(error_details) < 50:
                        error_details.append({
                            "category_id": leaf.get("id"),
                            "type_id": leaf.get("type_id"),
                            "error": f"DB commit failed: {e}",
                        })
            
            # ✅ ОЧИСТКА ПАМЯТИ после каждого чанка
            buffer.clear()
            gc.collect()

            logger.info(
                f"📦 Прогресс Ozon: {done_count}/{total} "
                f"(успех {fetched}, ошибок {errors})"
            )

    # Финальная очистка
    buffer.clear()
    gc.collect()

    logger.info(
        f"✅ Ozon refresh complete: fetched={fetched}, errors={errors}"
    )
    return {
        "platform": "ozon",
        "fetched": fetched,
        "errors": errors,
        "error_details": error_details,
    }