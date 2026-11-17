"""R35: жизненный цикл сессии — is_active, отзыв по jti, лимит пароля.

Закрывает замечания К-3 (деактивация убивает живые токены, logout отзывает
токен по jti), В-4 (гонка уникальности register → IntegrityError → 400),
В-5 (лимит пароля 72 байта bcrypt), В-7 (атомарный INCR+EXPIRE) и
В-12 (X-Request-ID).

Стиль проекта: чистые юнит-тесты без сети и БД — Request собирается
вручную, decode_token и Redis-функции подменяются стабами
(как в test_cookie_auth.py).
"""

import time

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import Response

import core.rate_limit as rate_limit
import routers.auth as auth_router
from core.auth import create_access_token, decode_token, get_current_user
from database.models import User
from models.schemas import UserCreate, UserLogin

# ---------------------------------------------------------------------------
# Стабы (в стиле test_cookie_auth.py)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalars(self):
        return self

    def first(self):
        return self._obj


class _FakeDB:
    """AsyncSession-стаб: execute() возвращает заготовленный объект."""

    def __init__(self, obj=None):
        self._obj = obj

    async def execute(self, *_a, **_k):
        return _FakeResult(self._obj)


def make_user(uid=1, role="user", is_active=True):
    return User(id=uid, username=f"u{uid}", email=f"u{uid}@x.io", role=role, is_active=is_active)


def make_request(method="GET", cookies=None, headers=None, token_bearer=None):
    raw_headers = []
    for k, v in (cookies or {}).items():
        raw_headers.append((b"cookie", f"{k}={v}".encode()))
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode(), v.encode()))
    if token_bearer:
        raw_headers.append((b"authorization", f"Bearer {token_bearer}".encode()))
    scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "headers": raw_headers,
        "query_string": b"",
    }
    return Request(scope)


def bearer(token: str):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def patch_decode(monkeypatch):
    """JWT-декодер возвращает заданный payload (по умолчанию — юзер 1)."""

    def _patch(payload=None):
        if payload is None:
            payload = {"sub": "1", "role": "user"}
        monkeypatch.setattr("core.auth.decode_token", lambda token: payload)

    return _patch


@pytest.fixture
def not_revoked(monkeypatch):
    """Блэклист пуст (как в Redis без отозванных токенов)."""
    monkeypatch.setattr("core.rate_limit.is_token_revoked", lambda jti: False)


# ---------------------------------------------------------------------------
# К-3: is_active убивает уже выданные токены
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inactive_user_token_rejected(patch_decode, not_revoked):
    """Деактивация админом убивает живую сессию, не только новые логины."""
    patch_decode({"sub": "1", "role": "user", "jti": "t1"})
    req = make_request(method="GET")
    with pytest.raises(HTTPException) as e:
        await get_current_user(req, bearer("jwt"), _FakeDB(make_user(is_active=False)))
    assert e.value.status_code == 401
    assert "деактивирован" in e.value.detail


@pytest.mark.asyncio
async def test_active_user_with_jti_passes(patch_decode, not_revoked):
    patch_decode({"sub": "1", "role": "user", "jti": "t1"})
    req = make_request(method="GET")
    user = await get_current_user(req, bearer("jwt"), _FakeDB(make_user()))
    assert user.id == 1


@pytest.mark.asyncio
async def test_revoked_jti_rejected(patch_decode, monkeypatch):
    """Токен из блэклиста (logout) отклоняется до похода в БД."""
    patch_decode({"sub": "1", "role": "user", "jti": "revoked-1"})
    monkeypatch.setattr("core.rate_limit.is_token_revoked", lambda jti: jti == "revoked-1")
    req = make_request(method="GET")
    with pytest.raises(HTTPException) as e:
        await get_current_user(req, bearer("jwt"), _FakeDB(make_user()))
    assert e.value.status_code == 401
    assert "отозван" in e.value.detail


@pytest.mark.asyncio
async def test_token_without_jti_skips_blacklist(patch_decode, monkeypatch):
    """Токен без jti (выдан до R35) блэклистом не проверяется — доживает до exp."""

    def _no_redis(*_a, **_k):
        raise AssertionError("is_token_revoked не должен вызываться для токена без jti")

    monkeypatch.setattr("core.rate_limit.is_token_revoked", _no_redis)
    patch_decode({"sub": "1", "role": "user"})
    req = make_request(method="GET")
    user = await get_current_user(req, bearer("jwt"), _FakeDB(make_user()))
    assert user.id == 1


# ---------------------------------------------------------------------------
# В-9: jti/iat в токене
# ---------------------------------------------------------------------------


def test_create_token_contains_iat_and_jti():
    token = create_access_token({"sub": "1"})
    payload = decode_token(token)
    assert payload["sub"] == "1"
    assert payload["jti"], "jti обязателен — на нём строится отзыв (logout)"
    assert payload["iat"], "iat обязателен — время выдачи токена"
    assert isinstance(payload["jti"], str) and len(payload["jti"]) == 32


def test_each_token_gets_unique_jti():
    a = decode_token(create_access_token({"sub": "1"}))
    b = decode_token(create_access_token({"sub": "1"}))
    assert a["jti"] != b["jti"], "разные логины = разные jti = независимый отзыв"


# ---------------------------------------------------------------------------
# Кэш payload: см. tests/test_auth_jwt_cache.py (один decode на запрос:
# повторные вызовы с тем же токеном берут request.state.jwt_payload)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# В-5: лимит пароля 72 байта (bcrypt)
# ---------------------------------------------------------------------------


def test_password_over_72_bytes_rejected():
    with pytest.raises(ValidationError):
        UserLogin(username="u", password="a" * 73)
    with pytest.raises(ValidationError):
        UserCreate(email="a@b.io", username="u", password="a" * 73)


def test_password_exactly_72_bytes_ok():
    assert UserLogin(username="u", password="a" * 72).password == "a" * 72


def test_password_byte_limit_not_char_limit():
    """40 кириллических символов = 80 байт: лимит именно по байтам."""
    with pytest.raises(ValidationError):
        UserLogin(username="u", password="пароль" * 10)  # 6 симв × 2 байта × 10


# ---------------------------------------------------------------------------
# В-4: гонка уникальности register → IntegrityError → 400
# ---------------------------------------------------------------------------


class _RaceDB:
    """Сессия, в которой pre-check уникальности прошёл, а INSERT упал
    (параллельная регистрация успела первой — реальная гонка в БД)."""

    def query(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return None  # дубля «не видно» — INSERT упадёт по unique-констрейнту

    def add(self, *_a):
        pass

    def commit(self):
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    def rollback(self):
        pass

    def close(self):
        pass

    def refresh(self, *_a):
        pass


def test_register_race_returns_400(monkeypatch):
    monkeypatch.setattr(auth_router, "SessionLocal", lambda: _RaceDB())
    from fastapi import BackgroundTasks

    req = make_request(method="POST")
    with pytest.raises(HTTPException) as e:
        auth_router.register.__wrapped__(
            UserCreate(email="a@b.io", username="dup", password="secret1"),
            req,
            BackgroundTasks(),
        )
    assert e.value.status_code == 400
    assert "уже существует" in e.value.detail


# ---------------------------------------------------------------------------
# К-3: logout отзывает токен по jti + атрибуты удаления кук
# ---------------------------------------------------------------------------


def test_logout_revokes_token_by_jti(monkeypatch):
    revoked = []
    monkeypatch.setattr(auth_router, "revoke_token", lambda jti, ttl: revoked.append((jti, ttl)))
    monkeypatch.setattr(auth_router, "log_access", lambda **_k: None)  # без БД

    req = make_request(method="POST", cookies={"access_token": "jwt-1"})
    # имитируем кэш от уже отработавшего get_current_user
    # (структура request.state — как в get_jwt_payload_cached)
    req.state.jwt_token = "jwt-1"
    req.state.jwt_payload = {"sub": "1", "jti": "jti-42", "exp": time.time() + 500}
    resp = Response()
    auth_router.logout.__wrapped__(req, resp, current_user=make_user())

    assert revoked and revoked[0][0] == "jti-42"
    assert 0 < revoked[0][1] <= 500, "TTL блэклиста = остаток жизни токена"


def test_logout_cookie_delete_attributes(monkeypatch):
    """delete_cookie повторяет атрибуты установки (path/samesite/secure)."""
    monkeypatch.setattr(auth_router, "log_access", lambda **_k: None)  # без БД
    req = make_request(method="POST")
    req.state.jwt_token = "jwt-1"
    req.state.jwt_payload = {"sub": "1"}
    resp = Response()
    auth_router.logout.__wrapped__(req, resp, current_user=make_user())

    set_cookies = resp.headers.getlist("set-cookie") if hasattr(resp.headers, "getlist") else []
    joined = "; ".join(set_cookies)
    assert "access_token=" in joined and "csrf_token=" in joined
    assert "Path=/" in joined
    assert "samesite=lax" in joined.lower(), "атрибуты удаления должны совпадать с установкой"


# ---------------------------------------------------------------------------
# В-7: атомарный INCR+EXPIRE (Lua) + блэклист-хелперы
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self):
        self.calls = {}

    def eval(self, script, numkeys, key, ttl):
        self.calls = {"script": script, "key": key, "ttl": ttl}
        return 2

    def setex(self, key, ttl, value):
        self.calls = {"key": key, "ttl": ttl, "value": value}

    def exists(self, key):
        self.calls = {"key": key}
        return 1


def test_incr_with_ttl_is_atomic_lua(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rate_limit, "_redis_client", fake)
    assert rate_limit._incr_with_ttl("violations:ip:1", 3600) == 2
    assert fake.calls["key"] == "violations:ip:1"
    assert fake.calls["ttl"] == 3600
    script = fake.calls["script"]
    assert (
        "INCR" in script and "EXPIRE" in script
    ), "скрипт обязан и инкрементировать, и ставить TTL"
    assert "if c == 1" in script, "TTL ставится только при первом инкременте"


def test_revoke_token_requires_positive_ttl(monkeypatch):
    """Блэклист не переживает сам токен: TTL <= 0 — записи нет."""
    fake = _FakeRedis()
    monkeypatch.setattr(rate_limit, "_redis_client", fake)
    rate_limit.revoke_token("jti", 0)
    rate_limit.revoke_token("", 100)
    assert fake.calls == {}


def test_is_token_revoked_without_jti_no_redis(monkeypatch):
    """Для токенов без jti (выданных до R35) в Redis идти не нужно."""

    class _Boom:
        @staticmethod
        def exists(_key):
            raise AssertionError("exists не должен вызываться для пустого jti")

    monkeypatch.setattr(rate_limit, "_redis_client", _Boom())
    assert rate_limit.is_token_revoked(None) is False
    assert rate_limit.is_token_revoked("") is False


def test_is_token_revoked_reads_prefix(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rate_limit, "_redis_client", fake)
    assert rate_limit.is_token_revoked("jti-1") is True
    assert fake.calls["key"] == f"{rate_limit.JWT_BLACKLIST_PREFIX}jti-1"


# ---------------------------------------------------------------------------
# В-12: X-Request-ID (Correlation-ID)
# ---------------------------------------------------------------------------


def test_request_id_echoed_and_generated(monkeypatch):
    from fastapi.testclient import TestClient

    import main as main_module
    from core.rate_limit import limiter

    # Redis в тестах недоступен: /api/health минует ban-check, но SlowAPI
    # полез бы в storage за лимитами — выключаем штатным флагом Limiter
    monkeypatch.setattr(limiter, "enabled", False)

    client = TestClient(main_module.app)

    # /api/health не требует Redis (ban-check исключает его)
    r1 = client.get("/api/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r1.status_code == 200
    assert r1.headers["x-request-id"] == "trace-abc-123", "входящий id возвращается эхом"

    r2 = client.get("/api/health")
    assert r2.status_code == 200
    assert r2.headers["x-request-id"], "без входящего id генерируется новый"
    assert len(r2.headers["x-request-id"]) == 16

    # недопустимый id (длиннее 64 символов) не эхом, а заменяется сгенерированным
    r3 = client.get("/api/health", headers={"X-Request-ID": "a" * 100})
    assert len(r3.headers["x-request-id"]) == 16 and r3.headers["x-request-id"] != "a" * 100
