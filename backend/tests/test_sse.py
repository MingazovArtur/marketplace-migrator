"""Round 8: SSE-стриминг прогресса задач (core/sse.py + эндпоинты).

Юнит-тесты генератора task_events:
  - первый кадр мгновенно, терминальный статус закрывает поток;
  - неизменные снимки не дублируются (дедуп), при молчании — keepalive;
  - разовая ошибка источника (моргание Redis/Celery) поток не роняет;
  - initial — готовый первый снимок без обращения к источнику.

Эндпоинт-тесты: кадры того же формата, что у polling-близнеца; 401 без
авторизации; paused — терминальный для загрузки спеков; мониторинг шлёт
снимок только при изменении и закрывается по лимиту времени; первый снимок
мониторинга, упавший с ошибкой, возвращает честный 5xx.

Тайминги SSE в тестах подменяются monkeypatch'ем констант core.sse —
иначе тесты спали бы секунды на реальных интервалах.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.sse as sse
import routers.migrate_router as migrate_router
from core.auth import get_current_user
from database.models import User
from routers.categories import specs_admin, specs_refresh


def make_user(uid=7, role="user"):
    return User(id=uid, username=f"u{uid}", email=f"u{uid}@x.io", role=role, is_active=True)


def payloads(text: str) -> list[dict]:
    """JSON-кадры из тела SSE-ответа (комментарии/keepalive пропускаем)."""
    return [
        json.loads(block[len("data: ") :])
        for block in text.split("\n\n")
        if block.startswith("data: ")
    ]


def make_app(*routers, user=None, prefix=""):
    app = FastAPI()
    for r in routers:
        # модули пакета categories не имеют своего префикса — его добавляет
        # агрегатор routers/categories/__init__.py; в тестах повторяем его же
        app.include_router(r, prefix=prefix)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


# ---------------------------------------------------------------------------
# task_events (генератор)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_frame_immediate_and_terminal_closes():
    states = iter(
        [
            {"status": "pending", "total": 2, "done": 0},
            {"status": "progress", "total": 2, "done": 1, "percent": 50},
            {"status": "completed", "total": 2, "done": 2, "percent": 100},
        ]
    )
    frames = [
        f
        async for f in sse.task_events(
            lambda: next(states), terminal=frozenset({"completed", "failed"}), poll_seconds=0
        )
    ]
    # 3 снимка — 3 кадра: мгновенный первый + промежуточный + терминальный
    assert [p["status"] for p in (json.loads(f[6:-2]) for f in frames)] == [
        "pending",
        "progress",
        "completed",
    ]
    assert all(f.startswith("data: ") and f.endswith("\n\n") for f in frames)


@pytest.mark.asyncio
async def test_unchanged_snapshots_deduplicated_with_keepalive():
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"status": "progress", "total": 5, "done": 1, "percent": 20}

    frames = [
        f
        async for f in sse.task_events(
            fetch,
            terminal=frozenset({"completed"}),
            poll_seconds=0.005,
            heartbeat_seconds=0.02,
            max_seconds=0.08,
        )
    ]
    data_frames = [f for f in frames if f.startswith("data: ")]
    keepalives = [f for f in frames if f.startswith(":")]

    # снимок не менялся: отправлен только первый кадр, дальше — keepalive
    assert len(data_frames) == 1
    assert len(keepalives) >= 1
    assert calls["n"] > 3  # источник продолжали опрашивать


@pytest.mark.asyncio
async def test_transient_fetch_error_does_not_kill_stream():
    states = iter([{"status": "pending"}, RuntimeError("redis blink"), {"status": "completed"}])

    def fetch():
        v = next(states)
        if isinstance(v, Exception):
            raise v
        return v

    frames = [
        f async for f in sse.task_events(fetch, terminal=frozenset({"completed"}), poll_seconds=0)
    ]
    assert [p["status"] for p in (json.loads(f[6:-2]) for f in frames)] == [
        "pending",
        "completed",
    ]


@pytest.mark.asyncio
async def test_initial_snapshot_used_without_first_fetch():
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"status": "completed", "total": 1, "done": 1}

    frames = [
        f
        async for f in sse.task_events(
            fetch,
            terminal=frozenset({"completed"}),
            initial={"status": "pending", "total": 1, "done": 0},
            poll_seconds=0,
        )
    ]
    statuses = [json.loads(f[6:-2])["status"] for f in frames]
    assert statuses == ["pending", "completed"]
    assert calls["n"] == 1  # первый кадр — из initial, источник дёргался один раз


# ---------------------------------------------------------------------------
# GET /api/migrate/batch/{id}/events
# ---------------------------------------------------------------------------


def test_migrate_events_stream(monkeypatch):
    states = iter(
        [
            {"status": "pending", "total": 3, "done": 0, "percent": 0},
            {"status": "progress", "total": 3, "done": 2, "percent": 66},
            {"status": "completed", "total": 3, "done": 3, "percent": 100},
        ]
    )
    monkeypatch.setattr(migrate_router, "get_progress", lambda task_id: next(states))
    monkeypatch.setattr(sse, "POLL_SECONDS", 0)

    app = make_app(migrate_router.router, user=make_user())
    r = TestClient(app).get("/api/migrate/batch/task-1/events")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    # X-Accel-Buffering: no — nginx не буферизует SSE-ответ
    assert r.headers["x-accel-buffering"] == "no"
    assert [p["status"] for p in payloads(r.text)] == ["pending", "progress", "completed"]


def test_migrate_events_requires_auth():
    app = make_app(migrate_router.router)
    r = TestClient(app).get("/api/migrate/batch/task-1/events")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/specs/{platform}/refresh/{task_id}/events
# ---------------------------------------------------------------------------


def test_specs_events_paused_is_terminal(monkeypatch):
    states = iter(
        [
            {"status": "progress", "total": 10, "done": 3, "percent": 30},
            {"status": "paused", "total": 10, "done": 10, "message": "остановлена админом"},
        ]
    )
    monkeypatch.setattr(specs_refresh, "get_progress", lambda task_id: next(states))
    monkeypatch.setattr(sse, "POLL_SECONDS", 0)

    app = make_app(specs_refresh.router, user=make_user(), prefix="/api")
    r = TestClient(app).get("/api/specs/ozon/refresh/task-9/events")

    assert r.status_code == 200
    assert [p["status"] for p in payloads(r.text)] == ["progress", "paused"]


def test_specs_events_requires_auth():
    app = make_app(specs_refresh.router, prefix="/api")
    r = TestClient(app).get("/api/specs/ozon/refresh/task-9/events")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/specs-tasks/events
# ---------------------------------------------------------------------------


def test_admin_events_stream_dedup_and_close(monkeypatch):
    snapshot = {"success": True, "active": [], "history": []}
    calls = {"n": 0}

    def fake_snapshot():
        calls["n"] += 1
        return snapshot

    monkeypatch.setattr(specs_admin, "_admin_snapshot", fake_snapshot)
    monkeypatch.setattr(specs_admin, "MONITOR_POLL_SECONDS", 0.005)
    monkeypatch.setattr(sse, "MAX_STREAM_SECONDS", 0.05)
    monkeypatch.setattr(sse, "HEARTBEAT_SECONDS", 1.0)  # без keepalive в тесте

    app = make_app(specs_admin.router, user=make_user(uid=1, role="admin"), prefix="/api")
    r = TestClient(app).get("/api/admin/specs-tasks/events")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    # снимок не менялся — отправлен только первый кадр, поток закрыт по лимиту
    assert payloads(r.text) == [snapshot]
    assert calls["n"] > 2  # реестр продолжали опрашивать


def test_admin_events_requires_admin():
    app = make_app(specs_admin.router, user=make_user(role="user"), prefix="/api")
    r = TestClient(app).get("/api/admin/specs-tasks/events")
    assert r.status_code == 403


def test_admin_events_first_snapshot_error_is_500(monkeypatch):
    def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(specs_admin, "_admin_snapshot", boom)
    app = make_app(specs_admin.router, user=make_user(uid=1, role="admin"), prefix="/api")
    r = TestClient(app, raise_server_exceptions=False).get("/api/admin/specs-tasks/events")
    # ошибка первого снимка — честный 5xx (как у GET /admin/specs-tasks), а не обрыв потока
    assert r.status_code == 500
