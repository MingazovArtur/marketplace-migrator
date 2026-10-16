"""
Загрузчик спецификаций категорий Яндекс Маркета через официальный Partner API.

Актуальные эндпоинты Partner API:
- POST /categories/tree                  → дерево всех категорий Маркета
- POST /category/{categoryId}/parameters → характеристики и словари значений листовой категории

Поддерживает современные API-ключи формата 'ACMA:...' (заголовок Api-Key)
и OAuth-токены (заголовок Authorization: OAuth).
"""

import asyncio
import gc
import hashlib
import json
import logging
from collections.abc import Callable
from datetime import datetime

import httpx

from database.models import PlatformCategorySpec
from database.session import SessionLocal

logger = logging.getLogger(__name__)

YANDEX_API_BASE = "https://api.partner.market.yandex.ru"

CONCURRENCY = 4          # одновременных запросов параметров категорий
TIMEOUT = 60.0           # таймаут одного HTTP-запроса
MAX_VALUES_PER_ATTR = 500
DB_CHUNK = 50            # категорий на один commit в БД
PROGRESS_EVERY = 10
MAX_RETRIES = 3

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


def _ym_headers(token: str) -> dict:
    """
    Формирует заголовки авторизации Яндекс Маркета:
    - Новые токены (ACMA:...) передаются в заголовке 'Api-Key'
    - Старые OAuth-токены (y0_...) — в 'Authorization: OAuth <token>'
    """
    clean = (token or "").strip()
    if clean.lower().startswith("oauth "):
        clean = clean[6:].strip()
        return {
            "Authorization": f"OAuth {clean}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    if clean.startswith("y0_"):
        return {
            "Authorization": f"OAuth {clean}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    return {
        "Api-Key": clean,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def _post_ym(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    path: str,
    body: dict,
    headers: dict,
) -> dict:
    """POST-запрос к Partner API Яндекс Маркета с семафором и retry на 420/429/5xx."""
    async with sem:
        last_err = None
        delay = 1.0
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(f"{YANDEX_API_BASE}{path}", json=body, headers=headers)
                if resp.status_code in (420, 429) or resp.status_code >= 500:
                    logger.warning(
                        f"⚠️ Yandex API {resp.status_code} на {path} (попытка {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (420, 429) or e.response.status_code >= 500:
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


# ========== Дерево категорий (POST /categories/tree) ==========


async def fetch_yandex_categories_tree(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    headers: dict,
) -> list[dict]:
    """
    Загружает полное дерево категорий Яндекс Маркета (POST /categories/tree)
    и возвращает список ЛИСТОВЫХ категорий в формате:
      {'id': '91491', 'name': 'Мобильные телефоны', 'full_name': 'Электроника / Мобильные телефоны', 'parent_id': '...'}
    """
    data = await _post_ym(client, sem, "/categories/tree", {"language": "RU"}, headers)
    root = data.get("result") or {}

    leaves: list[dict] = []

    def walk(node: dict, parent_id: str | None = None, parent_name: str | None = None):
        cat_id = node.get("id")
        cat_name = (node.get("name") or "").strip()
        children = node.get("children") or []

        if children:
            for ch in children:
                walk(
                    ch,
                    parent_id=str(cat_id) if cat_id else parent_id,
                    parent_name=cat_name if cat_name and cat_name != "Все товары" else parent_name,
                )
            return

        if not cat_id or not cat_name:
            return

        full_name = f"{parent_name} / {cat_name}" if parent_name else cat_name
        leaves.append(
            {
                "id": str(cat_id),
                "name": cat_name,
                "full_name": full_name,
                "parent_id": parent_id,
            }
        )

    walk(root)
    logger.info(f"🌳 Яндекс Маркет: найдено {len(leaves)} листовых категорий")
    return leaves


# ========== Характеристики категории (POST /category/{categoryId}/parameters) ==========


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


def _flush_ym_buffer(user_id: int, buffer: list[tuple[dict, dict]]) -> None:
    """Пакетное сохранение спеков Яндекс Маркета в БД."""
    if not buffer:
        return
    db = SessionLocal()
    try:
        for leaf, spec in buffer:
            cid = str(leaf["id"])
            cname = leaf.get("full_name") or leaf["name"]
            version = hashlib.sha256(
                json.dumps(spec, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()[:12]

            existing = (
                db.query(PlatformCategorySpec)
                .filter(
                    PlatformCategorySpec.platform == "yandex",
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
                db.add(
                    PlatformCategorySpec(
                        user_id=user_id,
                        platform="yandex",
                        category_id=cid,
                        category_name=cname,
                        parent_category_id=leaf.get("parent_id"),
                        spec=spec,
                        version=version,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ========== Оркестратор ==========


async def refresh_yandex_specs(
    user_id: int,
    token: str,
    business_id: str | None = None,
    category_ids: list[str] | None = None,
    progress_cb: Callable | None = None,
    concurrency: int = CONCURRENCY,
) -> dict:
    """
    Загружает дерево категорий Яндекс Маркета и их характеристики,
    сохраняя в platform_category_specs.
    """
    if not token or not token.strip():
        raise ValueError("Не указан API-ключ Яндекс Маркета (формат ACMA:...)")

    headers = _ym_headers(token)
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency + 4, max_keepalive_connections=concurrency)

    fetched = 0
    errors = 0
    error_details: list[dict] = []
    done_count = 0
    buffer: list[tuple[dict, dict]] = []

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits) as client:
        leaves = await fetch_yandex_categories_tree(client, sem, headers)

        if category_ids:
            wanted = {str(c).strip() for c in category_ids if str(c).strip()}
            leaves = [
                leaf
                for leaf in leaves
                if leaf["id"] in wanted
                or leaf["name"].lower() in {w.lower() for w in wanted}
            ]

        total = len(leaves)
        logger.info(
            f"🚀 Яндекс Маркет: к загрузке {total} категорий (business_id={business_id})"
        )

        if progress_cb:
            progress_cb({"total": total, "fetched": 0, "errors": 0})

        if total == 0:
            return {
                "platform": "yandex",
                "fetched": 0,
                "errors": 0,
                "error_details": [],
            }

        async def work(leaf: dict) -> None:
            nonlocal fetched, errors, done_count
            try:
                attrs = await fetch_yandex_category_parameters(client, sem, headers, leaf["id"])
                spec_content = {
                    "sheets": ["Список товаров", "Инструкция"],
                    "required_fields": YM_BASE_REQUIRED_FIELDS
                    + [a["name"] for a in attrs if a["required"]],
                    "attributes": attrs,
                    "validation_rules": _build_validation_rules(attrs),
                    "special_requirements": {
                        "yandex_category_name": leaf["name"],
                        "yandex_category_id": leaf["id"],
                    },
                }
                buffer.append((leaf, spec_content))
                fetched += 1
            except Exception as e:
                errors += 1
                if len(error_details) < 50:
                    error_details.append({"category_id": leaf["id"], "error": str(e)[:300]})
            finally:
                done_count += 1
                if progress_cb and (done_count % PROGRESS_EVERY == 0 or done_count == total):
                    progress_cb({"total": total, "fetched": fetched, "errors": errors})

        for i in range(0, total, DB_CHUNK):
            chunk = leaves[i : i + DB_CHUNK]
            await asyncio.gather(*(work(leaf) for leaf in chunk))
            try:
                _flush_ym_buffer(user_id, buffer)
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения чанка Яндекс Маркета: {e}")
                errors += len(buffer)
            buffer.clear()
            gc.collect()

    return {
        "platform": "yandex",
        "fetched": fetched,
        "errors": errors,
        "error_details": error_details,
    }