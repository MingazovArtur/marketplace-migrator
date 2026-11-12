"""Upsert спеков Wildberries в platform_category_specs."""

import hashlib
import json

from core.time import utcnow
from database.models import PlatformCategorySpec
from database.session import SessionLocal


def _upsert_spec(user_id, platform, category_id, category_name, parent_category_id, spec):
    db = SessionLocal()
    try:
        existing = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == platform,
                PlatformCategorySpec.category_id == category_id,
            )
            .first()
        )
        version = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]

        if existing:
            existing.user_id = user_id
            existing.category_name = category_name
            existing.parent_category_id = parent_category_id
            existing.spec = spec
            existing.version = version
            existing.fetched_at = utcnow()
        else:
            db.add(
                PlatformCategorySpec(
                    user_id=user_id,
                    platform=platform,
                    category_id=category_id,
                    category_name=category_name,
                    parent_category_id=parent_category_id,
                    spec=spec,
                    version=version,
                )
            )
        db.commit()
    finally:
        db.close()
