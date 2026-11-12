"""Round 8: WebP-миниатюры /media/thumbs (media_service + роутер).

Юнит-тесты генератора get_or_create_thumb:
  - WebP <= 320px по длинной стороне, пропорции сохранены;
  - кэш на диске: повторный запрос не перегенерирует;
  - EXIF-ориентация (снятые вертикально iPhone) выпрямляется;
  - битые файлы, не-изображения и path traversal отклоняются.

Эндпоинт-тесты GET /media/thumbs/{path}:
  - права идентичны /media: владелец/админ — 200 image/webp, чужой — 404;
  - файл миниатюры не отдаётся напрямую из дерева thumbs/ через catch-all;
  - вечный кэш (immutable) в заголовках.

Pillow в тестах обязателен: и оригиналы, и проверка результата — реальные
изображения (синтетика не покажет ни EXIF, ни пропорции).
"""

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import routers.media as media_router
from core.auth import get_current_user
from database.models import User
from database.session import get_async_db
from services import media_service


def make_user(uid=7, role="user"):
    return User(id=uid, username=f"u{uid}", email=f"u{uid}@x.io", role=role, is_active=True)


def jpeg_bytes(width=800, height=600, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Фикстуры: временное MEDIA_DIR роутера и MEDIA_ROOT сервиса — одно дерево
# ---------------------------------------------------------------------------


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    root = tmp_path / "media"
    (root / "products" / "7").mkdir(parents=True)
    (root / "products" / "7" / "img-abc.jpg").write_bytes(jpeg_bytes())
    # роутер и сервис обязаны смотреть в одно дерево (инвариант деплоя)
    monkeypatch.setattr(media_router, "MEDIA_DIR", root)
    monkeypatch.setattr(media_service, "MEDIA_ROOT", root)
    return root


class _FakeScalars:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return _FakeScalars(self._value)


class _FakeAsyncDB:
    """Async-сессия для ownership-проверки: селект товара возвращает id или None."""

    def __init__(self, owned_product_id):
        self._owned = owned_product_id

    async def execute(self, *args, **kwargs):
        return _FakeResult(self._owned)


@pytest.fixture
def make_client(media_dir):
    def _make(user, owned_product_id=7):
        app = FastAPI()
        app.include_router(media_router.router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_async_db] = lambda: _FakeAsyncDB(owned_product_id)
        return TestClient(app)

    return _make


# ---------------------------------------------------------------------------
# get_or_create_thumb (сервис)
# ---------------------------------------------------------------------------


def test_creates_webp_thumb_within_320px(media_dir):
    original = media_dir / "products" / "7" / "img-abc.jpg"
    thumb = media_service.get_or_create_thumb("products/7/img-abc.jpg", original)

    assert thumb is not None and thumb.is_file()
    with Image.open(thumb) as img:
        assert img.format == "WEBP"
        # 800x600 -> 320x240: предел по длинной стороне, пропорции сохранены
        assert img.size == (320, 240)


def test_thumb_is_cached_on_disk(media_dir):
    original = media_dir / "products" / "7" / "img-abc.jpg"
    first = media_service.get_or_create_thumb("products/7/img-abc.jpg", original)
    mtime = first.stat().st_mtime_ns

    second = media_service.get_or_create_thumb("products/7/img-abc.jpg", original)
    assert second == first
    # файл не перегенерировался (mtime не изменился) — кэш на диске работает
    assert second.stat().st_mtime_ns == mtime


def test_exif_orientation_is_straightened(media_dir):
    # JPEG 600x300 с EXIF Orientation=6: отображается как портрет 300x600 —
    # миниатюра обязана быть выпрямленной (портрет), а не «лежащей»
    img = Image.new("RGB", (600, 300), (10, 120, 30))
    exif = Image.Exif()
    exif[274] = 6  # Orientation
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)

    src = media_dir / "products" / "7" / "img-exif.jpg"
    src.write_bytes(buf.getvalue())

    thumb = media_service.get_or_create_thumb("products/7/img-exif.jpg", src)
    with Image.open(thumb) as t:
        assert t.size[0] < t.size[1]  # портрет: ширина < высоты


def test_rejects_broken_unsafe_and_non_images(media_dir):
    original = media_dir / "products" / "7" / "img-abc.jpg"

    # path traversal и дерево thumbs/ — не оригиналы
    assert media_service.get_or_create_thumb("../etc/passwd", original) is None
    assert media_service.get_or_create_thumb("thumbs/products/7/img-abc.jpg", original) is None
    # не-изображение по расширению
    assert media_service.get_or_create_thumb("products/7/nophoto.txt", original) is None
    # битый файл (байты не декодируются как изображение)
    broken = media_dir / "products" / "7" / "img-bad.jpg"
    broken.write_bytes(b"definitely not an image")
    assert media_service.get_or_create_thumb("products/7/img-bad.jpg", broken) is None


# ---------------------------------------------------------------------------
# GET /media/thumbs/{path} (роутер)
# ---------------------------------------------------------------------------


def test_owner_gets_webp_thumb(make_client):
    r = make_client(make_user(7), owned_product_id=7).get("/media/thumbs/products/7/img-abc.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    # миниатюра неизменима (имя оригинала детерминировано) — кэш навсегда
    assert "max-age=31536000" in r.headers["cache-control"]
    assert "immutable" in r.headers["cache-control"]
    with Image.open(io.BytesIO(r.content)) as img:
        assert img.format == "WEBP"


def test_foreign_user_gets_404(make_client):
    # селект товара владельца 7 ничего не вернул для юзера 8
    r = make_client(make_user(8), owned_product_id=None).get("/media/thumbs/products/7/img-abc.jpg")
    assert r.status_code == 404


def test_admin_gets_any_thumb(make_client):
    r = make_client(make_user(1, role="admin"), owned_product_id=None).get(
        "/media/thumbs/products/7/img-abc.jpg"
    )
    assert r.status_code == 200


def test_thumbs_tree_not_served_by_catch_all(make_client, media_dir):
    client = make_client(make_user(7), owned_product_id=7)
    r = client.get("/media/thumbs/products/7/img-abc.jpg")
    assert r.status_code == 200

    # файл миниатюры существует на диске (thumbs/products/7/img-abc.jpg.webp)...
    thumb_rel = media_service.thumb_path("products/7/img-abc.jpg").relative_to(media_dir)
    assert Path(media_dir / thumb_rel).is_file()
    # ...но напрямую из дерева thumbs/ catch-all его не отдаёт — ownership
    # проверяется только по пути ОРИГИНАЛА, поэтому thumbs/ в /media запрещён
    r2 = client.get(f"/media/{thumb_rel.as_posix()}")
    assert r2.status_code == 404


def test_missing_original_is_404(make_client):
    r = make_client(make_user(7), owned_product_id=7).get("/media/thumbs/products/7/nope.jpg")
    assert r.status_code == 404


def test_path_traversal_is_404(make_client):
    client = make_client(make_user(7), owned_product_id=7)
    # ../.. из URL (в т.ч. закодированные) не выводят за пределы MEDIA_DIR
    assert client.get("/media/thumbs/../../etc/passwd").status_code == 404
    assert client.get("/media/thumbs/products/7/..%2f..%2f..%2fetc%2fpasswd").status_code == 404


def test_requires_auth(media_dir):
    app = FastAPI()
    app.include_router(media_router.router)
    r = TestClient(app).get("/media/thumbs/products/7/img-abc.jpg")
    assert r.status_code == 401
