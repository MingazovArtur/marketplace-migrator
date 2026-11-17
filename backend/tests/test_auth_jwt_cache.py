"""Тесты кэша JWT-payload в request.state (R-35).

Раньше один и тот же Bearer-токен декодировался до трёх раз за запрос:
ban_check middleware → rate-limiter key_func → get_current_user.
Теперь первый вызов декодирует и кэширует payload, повторные — берут готовый.

Стиль проекта: чистые юнит-тесты без сети и БД — Request собирается
вручную (как в test_cookie_auth.py), декодер подменяется счётчиком.
"""

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

import core.auth as auth_core
from core.auth import get_current_user, get_jwt_payload_cached
from database.models import User

# ---------------------------------------------------------------------------
# Стабы
# ---------------------------------------------------------------------------


def make_request(headers=None, token_bearer=None):
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if token_bearer:
        raw_headers.append((b"authorization", f"Bearer {token_bearer}".encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "query_string": b"",
    }
    return Request(scope)


class _DecodeCounter:
    """Стаб decode_token: считает вызовы, возвращает заданный payload.

    payload="default" — валидный payload юзера 1; payload=None — «токен
       невалиден» (декодер всегда возвращает None, кэш писаться не должен).
    """

    def __init__(self, payload="default"):
        if payload == "default":
            payload = {"sub": "1", "role": "user"}
        self.payload = payload
        self.calls = 0

    def __call__(self, token):
        self.calls += 1
        return self.payload


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalars(self):
        return self

    def first(self):
        return self._obj


class _FakeDB:
    def __init__(self, obj=None):
        self._obj = obj

    async def execute(self, *_a, **_k):
        return _FakeResult(self._obj)


def make_user(uid=1):
    return User(id=uid, username=f"u{uid}", email=f"u{uid}@x.io", role="user", is_active=True)


# ---------------------------------------------------------------------------
# get_jwt_payload_cached
# ---------------------------------------------------------------------------


def test_second_call_same_token_no_redecode(monkeypatch):
    counter = _DecodeCounter()
    monkeypatch.setattr(auth_core, "decode_token", counter)
    req = make_request(token_bearer="tok-1")

    p1 = get_jwt_payload_cached(req, "tok-1")
    p2 = get_jwt_payload_cached(req, "tok-1")
    assert p1 is counter.payload
    assert p2 is counter.payload
    assert counter.calls == 1

    # безаргументный вызов (путь rate-limiter'а) тоже попадает в кэш
    p3 = get_jwt_payload_cached(req)
    assert p3 is counter.payload
    assert counter.calls == 1


def test_different_token_decodes_again(monkeypatch):
    counter = _DecodeCounter()
    monkeypatch.setattr(auth_core, "decode_token", counter)
    req = make_request(token_bearer="tok-1")

    get_jwt_payload_cached(req, "tok-1")
    get_jwt_payload_cached(req, "tok-2")
    assert counter.calls == 2


def test_invalid_token_not_cached(monkeypatch):
    """None (невалидный токен) не кэшируется — повторный вызов снова декодирует."""
    counter = _DecodeCounter(payload=None)
    monkeypatch.setattr(auth_core, "decode_token", counter)
    req = make_request(token_bearer="bad")

    assert get_jwt_payload_cached(req, "bad") is None
    assert get_jwt_payload_cached(req, "bad") is None
    assert counter.calls == 2


def test_no_bearer_header_returns_none(monkeypatch):
    counter = _DecodeCounter()
    monkeypatch.setattr(auth_core, "decode_token", counter)
    req = make_request()

    assert get_jwt_payload_cached(req) is None
    assert counter.calls == 0


def test_cookie_token_does_not_hit_bearer_cache(monkeypatch):
    """Кэш ключуется токеном: cookie-токен в кэш Bearer'а не подмешивается."""
    counter = _DecodeCounter()
    monkeypatch.setattr(auth_core, "decode_token", counter)
    req = make_request(token_bearer="tok-bearer")

    get_jwt_payload_cached(req, "tok-bearer")
    # get_current_user с cookie-токеном (другая строка) — штатный декод
    assert get_jwt_payload_cached(req, "tok-cookie") is counter.payload
    assert counter.calls == 2


# ---------------------------------------------------------------------------
# Интеграция с get_current_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_reuses_cache(monkeypatch):
    """middleware декодировал токен → get_current_user не декодирует повторно."""
    counter = _DecodeCounter()
    monkeypatch.setattr(auth_core, "decode_token", counter)
    req = make_request(token_bearer="tok-1")

    # 1) «ban_check middleware» уже декодировал и закэшировал payload
    get_jwt_payload_cached(req, "tok-1")

    # 2) get_current_user с тем же Bearer-токеном — кэш-хит, декод один
    user = await get_current_user(
        request=req,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok-1"),
        db=_FakeDB(make_user()),
    )
    assert user.id == 1
    assert counter.calls == 1
