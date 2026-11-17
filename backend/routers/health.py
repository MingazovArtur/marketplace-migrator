"""Healthcheck для Docker и мониторинга."""

from fastapi import APIRouter
from sqlalchemy import create_engine, text

from core.config import DATABASE_URL
from core.rate_limit import limiter

router = APIRouter(tags=["Health"])

_engine = create_engine(DATABASE_URL, pool_pre_ping=True)


@router.get("/api/health")
@limiter.exempt  # R29: healthcheck не должен зависеть от rate-limit (default_limits)
def health():
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}
