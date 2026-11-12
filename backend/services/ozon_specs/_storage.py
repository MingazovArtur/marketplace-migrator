"""Пакетная запись спеков Ozon в БД: upsert по (platform, category_id).

DB_CHUNK — политика чанкования (категорий на один commit), оркестратор
_refresh берёт её отсюда. Вынесено без изменений из монолита
services/ozon_specs.py (Р8).
"""

import hashlib
import json
import logging

from core.time import utcnow
from database.models import PlatformCategorySpec
from database.session import SessionLocal

logger = logging.getLogger(__name__)

DB_CHUNK = 50  # категорий на один commit (было 200)


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
                existing.fetched_at = utcnow()
            else:
                db.add(
                    PlatformCategorySpec(
                        user_id=user_id,
                        platform="ozon",
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
