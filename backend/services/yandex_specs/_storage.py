"""Пакетное сохранение спеков Яндекс Маркета в БД (upsert по platform+category_id)."""

import hashlib
import json

from core.time import utcnow
from database.models import PlatformCategorySpec
from database.session import SessionLocal

DB_CHUNK = 50  # категорий на один commit в БД


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
                existing.fetched_at = utcnow()
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
