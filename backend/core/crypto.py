"""
Шифрование секретных payloads (API-ключи маркетплейсов) для передачи через
Redis-брокер Celery (было В-4 из код-ревью: ключи лежали в Redis в открытом виде).

Схема: Fernet (AES-128-CBC + HMAC) с ключом, производным от settings.SECRET_KEY.
API и воркер живут в одном контуре (.env) — симметричное шифрование безопасно.

Формат: "enc1:<fernet-token>". Значения без префикса считаются legacy-plaintext
(задачи, поставленные в очередь ДО деплоя этого патча) и проходят как есть —
обратная совместимость без падений на релизе.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings

logger = logging.getLogger(__name__)

_PREFIX = "enc1:"


def _fernet_key() -> bytes:
    """Детерминированный Fernet-ключ из SECRET_KEY (SHA-256 → urlsafe base64)."""
    material = settings.SECRET_KEY.encode("utf-8")
    digest = hashlib.sha256(b"marketplace-migrator:celery-payload:v1:" + material).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_fernet_key())


def encrypt_str(value: str | None) -> str | None:
    """Шифрует строку для безопасной передачи через брокер."""
    if value is None:
        return None
    if value.startswith(_PREFIX):
        # Уже зашифровано (повторный вызов) — не шифруем дважды
        return value
    return _PREFIX + _fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_str(value: str | None) -> str | None:
    """
    Расшифровывает строку. Legacy-plaintext (без префикса) проходит как есть.
    При подмене/повреждении токена бросает ValueError — задача должна упасть громко,
    а не работать с испорченным ключом.
    """
    if value is None:
        return None
    if not value.startswith(_PREFIX):
        return value
    try:
        return _fernet.decrypt(value[len(_PREFIX) :].encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError(
            "Не удалось расшифровать секрет из Celery-payload "
            "(изменился SECRET_KEY или токен повреждён)"
        ) from e
