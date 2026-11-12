"""Опорные схемы и хелперы импорта товаров.

Вынесено без изменений из монолита routers/import_router.py (Р13):
  - MAX_IMPORT_FILE_SIZE — лимит загрузки файла (15 МБ)
  - _persist_imported_products — синхронная запись распарсенных товаров
    в БД (create/upsert + варианты + атрибуты); вызывается через
    asyncio.to_thread из async-роутов (B-1); P-2: одна сессия на весь
    импорт, один commit на чанк 200 товаров (repo.bulk_import)
  - ImportRequest — тело POST /import (единая точка получения ключа:
    поддерживает все варианты полей фронта)
  - _source_label — каноническая метка источника импорта из файла
  - _parse_yandex_api_credentials — разбор ключа Яндекс Маркета
    ('yandex:217055223:ACMA:...', '217055223:ACMA:...', 'ACMA:...',
    'businessId:токен')
"""

import os

from pydantic import BaseModel

from core.platforms import PLATFORM_CONFIG
from database.repository import repo

MAX_IMPORT_FILE_SIZE = 15 * 1024 * 1024  # 15 МБ


def _persist_imported_products(
    user_id: int, source_label: str, mode: str, products_data: list
) -> tuple[int, int]:
    """
    Синхронная запись распарсенных товаров в БД (create/upsert + варианты + атрибуты).
    Вызывается через asyncio.to_thread из async-роута — синхронные repo-вызовы
    не блокируют event loop (B-1). Возвращает (imported, updated).

    P-2 (неделя 3): запись переведена на repo.bulk_import — одна сессия на весь
    импорт, один commit на чанк (200 товаров), совпадения для upsert выбираются
    одним запросом на чанк. Было: 4 сессии и 2-4 commit'а на каждый товар,
    импорт 500 карточек = ~2000 сессий и ~1500 commit'ов.
    """
    return repo.bulk_import(
        user_id=user_id,
        source_label=source_label,
        mode=mode,
        products_data=products_data,
    )


class ImportRequest(BaseModel):
    key: str = ""
    full_key: str = ""
    auth_key: str = ""
    url: str = ""

    def get_key(self) -> str:
        """Единая точка получения ключа (поддерживает все варианты полей фронта)."""
        return (self.key or self.full_key or self.auth_key).strip()


def _source_label(platform: str) -> str:
    """Каноническая метка источника импорта из файла."""
    cfg = PLATFORM_CONFIG.get(platform) or {}
    return f"{cfg.get('name', platform)} (Файл)"


def _parse_yandex_api_credentials(raw_key: str) -> tuple[str, str] | None:
    """
    Разбирает строку ключа Яндекс Маркета.
    Поддерживаемые форматы:
      - 'yandex:217055223:ACMA:...'
      - '217055223:ACMA:...'
      - 'yandex:ACMA:...' (business_id берётся из YANDEX_BUSINESS_ID в .env)
      - 'ACMA:...'        (business_id берётся из YANDEX_BUSINESS_ID в .env)
    Возвращает (business_id, api_token) или None, если это не ключ Яндекса.
    """
    s = raw_key.strip()
    if s.lower().startswith("yandex:"):
        s = s[7:].strip()

    default_biz_id = os.getenv("YANDEX_BUSINESS_ID", "217055223").strip()

    # Вариант 1: сразу начинается с ACMA: или y0_
    if s.startswith(("ACMA:", "y0_")):
        if not default_biz_id:
            raise ValueError(
                "Укажите ID кабинета перед ключом через двоеточие: 'businessId:ACMA:...'"
            )
        return default_biz_id, s

    # Вариант 2: '<business_id>:<token>' (где token может быть 'ACMA:...:...')
    if ":" in s:
        first, rest = s.split(":", 1)
        if first.strip().isdigit() and (rest.startswith(("ACMA:", "y0_")) or len(rest) > 15):
            return first.strip(), rest.strip()

    return None
