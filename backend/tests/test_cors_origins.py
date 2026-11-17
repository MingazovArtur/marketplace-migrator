"""Н-1 из код-ревью: CORS-origins в production.

_build_cors_origins (main.py) строит список допустимых origins:
dev-адреса (localhost:5173/3000 и их 127.0.0.1-пары) допустимы
только вне production. Smoke-тест проверяет реальный middleware
(в conftest ENVIRONMENT=test → dev-origins включены).
"""

from fastapi.testclient import TestClient

from main import _build_cors_origins, app

LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def test_production_excludes_local_origins():
    origins = _build_cors_origins(
        is_production=True, configured=["https://app.example.com"]
    )
    assert origins == ["https://app.example.com"]


def test_production_empty_config_gives_no_origins():
    assert _build_cors_origins(is_production=True, configured=[]) == []


def test_dev_adds_local_origins():
    origins = _build_cors_origins(
        is_production=False, configured=["https://app.example.com"]
    )
    assert origins[:4] == LOCAL_ORIGINS
    assert origins[-1] == "https://app.example.com"


def test_dev_deduplicates_configured():
    origins = _build_cors_origins(
        is_production=False,
        configured=["http://localhost:5173", "https://a.example.com"],
    )
    assert origins.count("http://localhost:5173") == 1
    assert "https://a.example.com" in origins


def test_preflight_from_dev_origin_allowed():
    """Preflight от Vite-дев-сервера получает CORS-заголовки (smoke)."""
    client = TestClient(app)
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert resp.headers["access-control-allow-credentials"] == "true"
