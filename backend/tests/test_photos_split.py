"""Р21: гарантия, что разбиение routers/photos.py (298 строк) на пакет
routers/photos/ не потеряло маршруты, их порядок и публичный API монолита.

Сверяет таблицу (path, method) всех 5 эндпоинтов через OpenAPI-схему
(served_routes) и отдельно фиксирует ПОРЯДОК регистрации: фиксированный
GET /photos/proxy обязан идти раньше параметрических
/{product_id}/photos — как в монолите (иначе матчинг маршрутов меняется).

Прокси-эндпоинт через TestClient не дёргается: он под rate-limiter'ом
(slowapi + Redis), тестовое окружение без Redis; логика SSRF-фильтра
покрыта tests/test_ssrf.py на уровне core.ssrf.safe_get.
"""

import _route_helpers

import routers.photos as pkg
from routers.photos._download import start_download_photos as from_download
from routers.photos._manage import get_photos as from_manage_get
from routers.photos._manage import set_photos as from_manage_put
from routers.photos._proxy import proxy_external_photo as from_proxy
from routers.photos._support import (
    ALLOWED_EXTENSIONS as support_allowed,
)
from routers.photos._support import (
    MAX_FILE_SIZE_BYTES as support_max_file,
)
from routers.photos._support import (
    MAX_PHOTOS_PER_PRODUCT as support_max_photos,
)
from routers.photos._support import (
    PhotosUpdate as support_model,
)
from routers.photos._support import (
    _build_public_media_url as from_support,
)
from routers.photos._upload import upload_photo_files as from_upload

EXPECTED_ROUTES = {
    ("/api/products/photos/proxy", "GET"),
    ("/api/products/{product_id}/photos", "GET"),
    ("/api/products/{product_id}/photos", "PUT"),
    ("/api/products/{product_id}/photos/upload", "POST"),
    ("/api/products/{product_id}/photos/download", "POST"),
}


def test_routes_preserved():
    actual = _route_helpers.served_routes(pkg.router)
    assert actual == EXPECTED_ROUTES
    # полный список маршрутов монолита — без потерь и лишних
    assert len(actual) == 5


def test_proxy_route_registered_before_parametric():
    """Порядок include_router сохранён как в монолите: фиксированный
    /photos/proxy регистрируется раньше параметрических /{product_id}/..."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(pkg.router)
    paths = [p for p in app.openapi()["paths"] if "photos" in p]
    assert (
        paths[0] == "/api/products/photos/proxy"
    ), f"/photos/proxy обязан идти первым, фактически: {paths}"
    assert all("{product_id}" in p for p in paths[1:])


def test_prefix_and_tag():
    assert pkg.router.prefix == "/api/products"
    assert "Photos" in pkg.router.tags


def test_public_api_preserved():
    """Все публичные имена монолита остались на пакете — те же объекты,
    что в подмодулях (импортёр main.py использует только photos.router)."""
    assert pkg.proxy_external_photo is from_proxy
    assert pkg.get_photos is from_manage_get
    assert pkg.set_photos is from_manage_put
    assert pkg.upload_photo_files is from_upload
    assert pkg.start_download_photos is from_download
    assert pkg.PhotosUpdate is support_model
    assert pkg._build_public_media_url is from_support
    assert pkg.ALLOWED_EXTENSIONS is support_allowed
    assert pkg.MAX_FILE_SIZE_BYTES is support_max_file
    assert pkg.MAX_PHOTOS_PER_PRODUCT is support_max_photos

    # лимиты монолита не изменились
    assert {".jpg", ".jpeg", ".png", ".webp"} == pkg.ALLOWED_EXTENSIONS
    assert pkg.MAX_FILE_SIZE_BYTES == 10 * 1024 * 1024
    assert pkg.MAX_PHOTOS_PER_PRODUCT == 30
    assert pkg.PROXY_MAX_SIZE_BYTES == 10 * 1024 * 1024
    assert "image/jpeg" in pkg.PROXY_ALLOWED_CONTENT_TYPES
    assert "text/html" not in pkg.PROXY_ALLOWED_CONTENT_TYPES

    # полный каталог поверхности пакета
    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {
        "ALLOWED_EXTENSIONS",
        "APIRouter",
        "MAX_FILE_SIZE_BYTES",
        "MAX_PHOTOS_PER_PRODUCT",
        "PROXY_ALLOWED_CONTENT_TYPES",
        "PROXY_MAX_SIZE_BYTES",
        "PhotosUpdate",
        "download_router",
        "get_photos",
        "manage_router",
        "proxy_external_photo",
        "proxy_router",
        "router",
        "set_photos",
        "start_download_photos",
        "upload_photo_files",
        "upload_router",
    }


def _client_with_user():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from core.auth import get_current_user
    from database.models import User

    app = FastAPI()
    app.include_router(pkg.router)
    user = User(id=7, username="u7", email="u7@x.io", role="user", is_active=True)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_set_photos_dedups_and_updates(monkeypatch):
    import routers.photos._manage as manage_mod

    updated = {}

    class _FakeRepo:
        def get_by_id(self, product_id, user_id=None):
            return {"id": product_id, "photos": ["http://x/1.jpg"]}

        def update(self, product_id, data, user_id=None):
            updated["product_id"] = product_id
            updated.update(data)

    monkeypatch.setattr(manage_mod, "repo", _FakeRepo())
    client = _client_with_user()

    r = client.put(
        "/api/products/5/photos",
        json={"photos": ["http://x/2.jpg", "http://x/2.jpg", "", " http://x/3.jpg "]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # дубликаты и пустые URL отброшены, порядок сохранён
    assert body["photos"] == ["http://x/2.jpg", "http://x/3.jpg"]
    assert body["count"] == 2
    assert updated["product_id"] == 5
    assert updated["photos"] == ["http://x/2.jpg", "http://x/3.jpg"]
    assert updated["photos_count"] == 2


def test_set_photos_rejects_over_limit(monkeypatch):
    import routers.photos._manage as manage_mod

    class _FakeRepo:
        def get_by_id(self, product_id, user_id=None):
            return {"id": product_id, "photos": []}

        def update(self, *a, **k):
            raise AssertionError("update не должен вызываться при превышении лимита")

    monkeypatch.setattr(manage_mod, "repo", _FakeRepo())
    client = _client_with_user()

    r = client.put(
        "/api/products/5/photos",
        json={"photos": [f"http://x/{i}.jpg" for i in range(pkg.MAX_PHOTOS_PER_PRODUCT + 1)]},
    )
    assert r.status_code == 400
    assert str(pkg.MAX_PHOTOS_PER_PRODUCT) in r.json()["detail"]


def test_set_photos_requires_auth():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(pkg.router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.put("/api/products/5/photos", json={"photos": []})
    assert r.status_code == 401  # без токена доступ закрыт (как в монолите)


def test_build_public_media_url_variants(monkeypatch):
    from routers.photos._support import settings

    class _FakeURL(str):
        pass

    class _FakeRequest:
        base_url = "http://backend:8000/"

    monkeypatch.setattr(settings, "PUBLIC_URL", "")
    assert (
        from_support(_FakeRequest(), "products/5/x.jpg")
        == "http://backend:8000/media/products/5/x.jpg"
    )

    monkeypatch.setattr(settings, "PUBLIC_URL", "http://localhost:5173")
    # dev-фронт подставлять нельзя: XLSX-экспорт получает адрес бэкенда
    assert from_support(_FakeRequest(), "x.jpg") == "http://backend:8000/media/x.jpg"

    monkeypatch.setattr(settings, "PUBLIC_URL", "https://cdn.example.com/")
    assert from_support(_FakeRequest(), "/x.jpg") == "https://cdn.example.com/media/x.jpg"
