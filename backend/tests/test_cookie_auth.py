"""Тесты cookie-аутентификации + CSRF (double-submit) + /media ownership.

Стиль проекта: чистые юнит-тесты без сети и БД — Request собирается вручную,
decode_token и БД подменяются стабами.
"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

import core.auth as auth_core
import routers.media as media_router
from core.auth import get_current_user
from database.models import User


# ---------------------------------------------------------------------------
# Стабы
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


def make_user(uid=1, role="user"):
    return User(id=uid, username=f"u{uid}", email=f"u{uid}@x.io", role=role, is_active=True)


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
    """JWT-декодер всегда возвращает валидный payload для юзера 1."""

    def _patch(payload={"sub": "1", "role": "user"}):
        monkeypatch.setattr(auth_core, "decode_token", lambda token: payload)

    return _patch


# ---------------------------------------------------------------------------
# Приём токена: Bearer ИЛИ httpOnly-cookie
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bearer_token_accepted(patch_decode):
    patch_decode()
    req = make_request(method="GET")
    user = await get_current_user(req, bearer("jwt-123"), _FakeDB(make_user()))
    assert user.id == 1


@pytest.mark.asyncio
async def test_cookie_token_accepted(patch_decode):
    patch_decode()
    req = make_request(method="GET", cookies={"access_token": "jwt-123"})
    user = await get_current_user(req, None, _FakeDB(make_user()))
    assert user.id == 1


@pytest.mark.asyncio
async def test_no_token_401(patch_decode):
    patch_decode()
    req = make_request(method="GET")
    with pytest.raises(HTTPException) as e:
        await get_current_user(req, None, _FakeDB(make_user()))
    assert e.value.status_code == 401


# ---------------------------------------------------------------------------
# CSRF: double-submit (заголовок X-CSRF-Token == кука csrf_token)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cookie_post_without_csrf_403(patch_decode):
    """Мутация через куку без CSRF-заголовка — 403 (ядро CSRF-защиты)."""
    patch_decode()
    req = make_request(method="POST", cookies={"access_token": "jwt", "csrf_token": "abc"})
    with pytest.raises(HTTPException) as e:
        await get_current_user(req, None, _FakeDB(make_user()))
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_cookie_post_with_wrong_csrf_403(patch_decode):
    patch_decode()
    req = make_request(
        method="POST",
        cookies={"access_token": "jwt", "csrf_token": "abc"},
        headers={"X-CSRF-Token": "spoofed"},
    )
    with pytest.raises(HTTPException) as e:
        await get_current_user(req, None, _FakeDB(make_user()))
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_cookie_post_with_matching_csrf_ok(patch_decode):
    patch_decode()
    req = make_request(
        method="POST",
        cookies={"access_token": "jwt", "csrf_token": "abc"},
        headers={"X-CSRF-Token": "abc"},
    )
    user = await get_current_user(req, None, _FakeDB(make_user()))
    assert user.id == 1


@pytest.mark.asyncio
async def test_cookie_get_without_csrf_ok(patch_decode):
    """GET через куку CSRF не требует (идемпотентный)."""
    patch_decode()
    req = make_request(method="GET", cookies={"access_token": "jwt"})
    user = await get_current_user(req, None, _FakeDB(make_user()))
    assert user.id == 1


@pytest.mark.asyncio
async def test_bearer_post_without_csrf_ok(patch_decode):
    """Bearer-клиенты CSRF не проходят: токен с чужого сайта не подставить."""
    patch_decode()
    req = make_request(method="POST")
    user = await get_current_user(req, bearer("jwt"), _FakeDB(make_user()))
    assert user.id == 1


# ---------------------------------------------------------------------------
# /media: ownership + path traversal
# ---------------------------------------------------------------------------

@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    (tmp_path / "products" / "1").mkdir(parents=True)
    (tmp_path / "products" / "1" / "img-a.jpg").write_bytes(b"jpegdata")
    (tmp_path / "products" / "2").mkdir(parents=True)
    (tmp_path / "products" / "2" / "img-b.jpg").write_bytes(b"jpegdata")
    monkeypatch.setattr(media_router, "MEDIA_DIR", tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_media_owner_ok(patch_decode, media_dir):
    patch_decode()
    req = make_request(method="GET", cookies={"access_token": "jwt"})
    # юзер 1 владеет продуктом 1 (БД-стаб возвращает id)
    res = await media_router.get_media(
        "products/1/img-a.jpg", current_user=make_user(1), db=_FakeDB(1)
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_media_foreign_product_404(patch_decode, media_dir):
    patch_decode()
    # юзер 1 НЕ владеет продуктом 2 (БД-стаб: None) -> 404, а не 403
    with pytest.raises(HTTPException) as e:
        await media_router.get_media(
            "products/2/img-b.jpg", current_user=make_user(1), db=_FakeDB(None)
        )
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_media_admin_sees_all(patch_decode, media_dir):
    patch_decode()
    res = await media_router.get_media(
        "products/2/img-b.jpg", current_user=make_user(1, role="admin"), db=_FakeDB(None)
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_media_path_traversal_404(patch_decode, media_dir):
    patch_decode()
    (media_dir / "secret.txt").write_text("top secret")
    for bad in (
        "../secret.txt",
        "products/1/../../secret.txt",
        "/etc/passwd",
        "products/1/%2e%2e/secret.txt",
    ):
        with pytest.raises(HTTPException) as e:
            await media_router.get_media(bad, current_user=make_user(1), db=_FakeDB(1))
        assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_media_wrong_extension_404(patch_decode, media_dir):
    patch_decode()
    (media_dir / "products" / "1" / "notes.html").write_text("<h1>hi</h1>")
    with pytest.raises(HTTPException) as e:
        await media_router.get_media(
            "products/1/notes.html", current_user=make_user(1), db=_FakeDB(1)
        )
    assert e.value.status_code == 404
