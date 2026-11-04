"""Тесты шифрования Celery-payload (неделя 2, В-4): encrypt_str/decrypt_str."""

import pytest

from core.crypto import decrypt_str, encrypt_str


def test_roundtrip():
    token = "sk-api-12345-секретный-ключ"
    encrypted = encrypt_str(token)
    assert encrypted.startswith("enc1:")
    assert token not in encrypted
    assert decrypt_str(encrypted) == token


def test_none_passthrough():
    assert encrypt_str(None) is None
    assert decrypt_str(None) is None


def test_legacy_plaintext_passthrough():
    """Значения без префикса enc1: (задачи из очереди до деплоя) проходят как есть."""
    assert decrypt_str("legacy-plaintext-token") == "legacy-plaintext-token"


def test_double_encrypt_is_idempotent():
    once = encrypt_str("value")
    assert encrypt_str(once) == once


def test_tampered_token_raises_value_error():
    encrypted = encrypt_str("value")
    token_part = encrypted[len("enc1:"):]
    tampered = encrypted[: len("enc1:")] + ("A" if token_part[-1] != "A" else "B") + token_part[:-1]
    assert tampered != encrypted
    with pytest.raises(ValueError, match="расшифровать"):
        decrypt_str(tampered)


def test_token_is_not_deterministic():
    """Fernet использует случайный IV: два шифрования одного значения различны."""
    assert encrypt_str("same-value") != encrypt_str("same-value")
