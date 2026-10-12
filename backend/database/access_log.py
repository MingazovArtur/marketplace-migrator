"""Журнал доступа. Автономный модуль: не ломает auth, если БД недоступна."""

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL
from database.models import AccessLog

logger = logging.getLogger(__name__)
_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
_Session = sessionmaker(bind=_engine)


def get_client_ip(request) -> str:
    """Реальный IP клиента за nginx (X-Forwarded-For / X-Real-IP)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else "unknown"


def log_access(*, user_id=None, username=None, action: str, ip: str = None, user_agent: str = None):
    try:
        with _Session() as s:
            s.add(
                AccessLog(
                    user_id=user_id,
                    username=username,
                    action=action,
                    ip=(ip or "")[:64],
                    user_agent=(user_agent or "")[:512],
                )
            )
            s.commit()
    except Exception as e:
        logger.warning(f"access log failed: {e}")  # журнал не должен ронять auth
