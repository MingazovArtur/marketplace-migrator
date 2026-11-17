"""Конфигурация логирования (R35, В-12 ревью).

Было: logging.basicConfig(level=INFO) прямо в main.py — глобально,
без формата (без даты) и без склейки сообщений одного запроса.

Теперь:
- формат «дата уровень [request_id] имя: сообщение»;
- request_id подставляется ContextVar-фильтром: middleware в main.py
  кладёт туда X-Request-ID запроса, фильтр дописывает поле в каждую
  запись, доходящую до root (включая логгеры библиотек);
- уровень берётся из settings.LOG_LEVEL (env LOG_LEVEL);
- если root уже настроен снаружи (pytest, gunicorn) — ничего не
  переустанавливаем.
"""

import logging
from contextvars import ContextVar

from core.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Дописывает record.request_id из ContextVar (для формата %(request_id)s)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging() -> None:
    """Настроить root-логгер, если он ещё не настроен снаружи."""
    root = logging.getLogger()
    if root.handlers:  # уже настроено (pytest/gunicorn/uvicorn) — не мешаем
        return

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
    )
    rid_filter = RequestIdFilter()
    for handler in root.handlers:
        handler.addFilter(rid_filter)
