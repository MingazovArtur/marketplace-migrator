"""Журнал доступа. Автономный модуль: не ломает auth, если БД недоступна."""

import ipaddress
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL
from database.models import AccessLog

logger = logging.getLogger(__name__)
_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
_Session = sessionmaker(bind=_engine)


def _valid_ip(value: str) -> str | None:
    """Возвращает значение, если это корректный IP, иначе None."""
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        return None


def get_client_ip(request) -> str:
    """
    Реальный IP клиента за nginx.

    Было (K-3, дубликат дыры из core.rate_limit): брался ПЕРВЫЙ элемент
    X-Forwarded-For — его контролирует клиент, что позволяло писать в журнал
    доступа поддельные IP. Логика синхронизирована с core.rate_limit:

      1) X-Real-IP — проставляет наш nginx, значение клиента перезаписывается;
      2) X-Forwarded-For — только ПОСЛЕДНИЙ (правый) элемент, добавленный nginx;
      3) request.client.host — прямое соединение (dev без прокси).
    """
    xri = request.headers.get("x-real-ip")
    if xri:
        ip = _valid_ip(xri.strip())
        if ip:
            return ip

    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            ip = _valid_ip(parts[-1])
            if ip:
                return ip

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
