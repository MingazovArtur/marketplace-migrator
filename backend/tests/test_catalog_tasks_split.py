"""Р22: гарантия, что разбиение tasks/catalog_tasks.py (297 строк) на пакет
сохранило публичный API, регистрацию Celery-задачи и поведение.

Импортёр один — tasks/__init__.py: `from tasks.catalog_tasks import
refresh_specs_task` (не менялся). Имя задачи явное (name="tasks.refresh_specs_task"):
регистрация декоратором в подмодуле _refresh и маршрутизация очередей
(celery_app.py: task_routes → очередь specs) от пути модуля не зависят.
Обработчик worker_ready подключается в _reconcile при импорте пакета
(side-effect), как раньше при импорте монолита.

Поведение проверяем без брокера: зависимости подменяем в подмодуле _refresh
(прецедент — test_migrate_tasks_split.py), загрузчики спеков — по месту их
локального импорта (services.ozon_specs / services.yandex_specs /
services.wb_specs), задачу выполняем eager-вызовом .apply(throw=True).
"""

import pytest

import tasks.catalog_tasks as pkg
import tasks.catalog_tasks._refresh as refresh_mod
from tasks.catalog_tasks._refresh import refresh_specs_task as from_refresh


class _FakeSpecsMonitor:
    """Стаб реестра мониторинга: пишет вызовы, pause_requested управляется тестом."""

    def __init__(self, pause_requested=False):
        self.calls = []
        self._pause = pause_requested

    def finish(self, task_id, **kw):
        self.calls.append(("finish", kw))

    def set_running(self, task_id, **kw):
        self.calls.append(("set_running", kw))

    def pause_requested(self, task_id):
        return self._pause

    def clear_pause(self, task_id):
        self.calls.append(("clear_pause", {}))

    def sync_done_keys(self, task_id, keys):
        self.calls.append(("sync_done_keys", sorted(keys)))


class _FakeStatsRepo:
    def __init__(self):
        self.records = []

    def record(self, **kw):
        self.records.append(kw)


class _FakeCache:
    def __init__(self):
        self.deleted = []

    def delete_pattern(self, pattern):
        self.deleted.append(pattern)


def _stub_shared(monkeypatch, *, pause=False):
    monitor = _FakeSpecsMonitor(pause_requested=pause)
    stats = _FakeStatsRepo()
    cache = _FakeCache()
    monkeypatch.setattr(refresh_mod, "specs_monitor", monitor)
    monkeypatch.setattr(refresh_mod, "stats_repo", stats)
    monkeypatch.setattr(refresh_mod, "cache_service", cache)
    invalidated = []
    monkeypatch.setattr(refresh_mod, "_spec_cache_invalidate", lambda p=None: invalidated.append(p))
    monkeypatch.setattr("core.crypto.decrypt_str", lambda s: s)
    return monitor, stats, cache, invalidated


def test_public_api_preserved():
    from tasks.catalog_tasks._reconcile import (
        _reconcile_specs_registry_on_worker_start as from_reconcile,
    )

    assert pkg.refresh_specs_task is from_refresh
    assert pkg._reconcile_specs_registry_on_worker_start is from_reconcile
    # `from tasks import refresh_specs_task` — единственный публичный импортёр не менялся
    from tasks import refresh_specs_task

    assert refresh_specs_task is pkg.refresh_specs_task
    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {"refresh_specs_task"}


def test_task_registered_and_queue():
    from celery_app import celery_app

    registered = celery_app.tasks["tasks.refresh_specs_task"]
    assert registered.name == "tasks.refresh_specs_task"
    assert registered.run.__module__ == "tasks.catalog_tasks._refresh"
    # маршрутизация очередей — по явному имени, не по пути модуля
    route = celery_app.conf.task_routes.get("tasks.refresh_specs_task")
    assert route and route.get("queue") == "specs"


def test_worker_ready_receiver_connected():
    from celery.signals import worker_ready

    names = [
        getattr(r, "__name__", "")
        for r in worker_ready._live_receivers(None)
    ]
    assert "_reconcile_specs_registry_on_worker_start" in names


def test_refresh_task_unknown_platform_is_error(monkeypatch):
    monitor, stats, cache, invalidated = _stub_shared(monkeypatch)

    result = pkg.refresh_specs_task.apply(
        args=[7, "aliexpress", "key"], throw=True
    ).get()

    assert result["status"] == "error"
    assert result["platform"] == "aliexpress"
    assert result["errors"] == 1
    # реестр: running -> error; статистика ошибки записана
    kinds = [c[0] for c in monitor.calls]
    assert kinds[0] == "set_running" and "finish" in kinds
    assert stats.records and stats.records[0]["status"] == "error"
    # кэши при падении не трогаем
    assert not cache.deleted and not invalidated


def test_refresh_task_paused_from_queue(monkeypatch):
    monitor, stats, cache, invalidated = _stub_shared(monkeypatch, pause=True)

    result = pkg.refresh_specs_task.apply(
        args=[7, "ozon", "key"], throw=True
    ).get()

    assert result["status"] == "paused"
    assert result["total"] == 0 and result["percent"] == 0
    kinds = [c[0] for c in monitor.calls]
    assert kinds == ["set_running", "clear_pause", "finish"]
    finish_kw = monitor.calls[-1][1]
    assert finish_kw["status"] == "paused"
    # снялись с старта, не тратя API-лимиты: ни кэшей, ни статистики
    assert not cache.deleted and not invalidated and not stats.records


@pytest.mark.parametrize("platform,loader_path", [
    ("ozon", "services.ozon_specs.refresh_ozon_specs"),
    ("yandex", "services.yandex_specs.refresh_yandex_specs"),
    ("wildberries", "services.wb_specs.refresh_wildberries_specs"),
])
def test_refresh_task_success_flow(monkeypatch, platform, loader_path):
    monitor, stats, cache, invalidated = _stub_shared(monkeypatch)
    loaded = {}

    async def _fake_loader(**kw):
        loaded["kw"] = kw
        return {"fetched": 2, "errors": 0, "error_details": []}

    monkeypatch.setattr(loader_path, _fake_loader)

    result = pkg.refresh_specs_task.apply(
        args=[7, platform, "key"], throw=True
    ).get()

    assert result == {
        "status": "completed",
        "platform": platform,
        "total": 2,
        "done": 2,
        "success": 2,
        "fetched": 2,
        "errors": 0,
        "percent": 100,
        "error_details": [],
        "duration_ms": result["duration_ms"],
    }
    # оркестратор передал загрузчику расшифрованный ключ и колбэки паузы/прогресса
    kw = loaded["kw"]
    assert kw["user_id"] == 7
    assert callable(kw["progress_cb"]) and callable(kw["pause_check"])
    assert kw["pause_check"]() is False
    kw["progress_cb"]({"total": 2, "fetched": 2, "errors": 0})  # не падает (eager)
    # реестр закрыт успехом, статистика и кэши сброшены
    finish_kw = monitor.calls[-1][1]
    assert finish_kw["status"] == "success"
    assert stats.records[0]["status"] == "success"
    assert sorted(cache.deleted) == [f"categories:{platform}:*", f"specs:{platform}:*"]
    assert invalidated == [platform]


def test_refresh_task_paused_mid_run(monkeypatch):
    monitor, stats, cache, invalidated = _stub_shared(monkeypatch)

    async def _fake_loader(**kw):
        # админ нажал паузу во время загрузки: часть категорий сохранена
        kw["done_keys"].update({"101", "102"})
        return {"fetched": 1, "errors": 0, "paused": True}

    monkeypatch.setattr("services.ozon_specs.refresh_ozon_specs", _fake_loader)

    result = pkg.refresh_specs_task.apply(
        args=[7, "ozon", "key"], kwargs={"skip_category_ids": ["100"]},
        throw=True,
    ).get()

    assert result["status"] == "paused"
    assert result["fetched"] == 1 and result["message"]
    kinds = [c[0] for c in monitor.calls]
    assert kinds == ["set_running", "clear_pause", "finish"]
    finish_kw = monitor.calls[-1][1]
    assert finish_kw["status"] == "paused"
    # прогресс для resume: ключи сохранённых категорий ушли в реестр
    assert monitor.calls[-1][1]["done_keys"] == ["100", "101", "102"]
    # частично загруженные спеки уже в БД — кэши сброшены как обычно
    assert invalidated == ["ozon"]
    assert sorted(cache.deleted) == ["categories:ozon:*", "specs:ozon:*"]
    # статистика на паузе не пишется
    assert not stats.records


def test_refresh_task_bad_api_key_fails_loud(monkeypatch):
    monitor, stats, cache, invalidated = _stub_shared(monkeypatch)

    def _boom(raw):
        raise ValueError("Повреждённый токен")

    monkeypatch.setattr("core.crypto.decrypt_str", _boom)

    # громкий падёж задачи: реестр закрыт error, исключение прокинуто
    with pytest.raises(ValueError):
        pkg.refresh_specs_task.apply(args=[7, "ozon", "key"], throw=True)

    kinds = [c[0] for c in monitor.calls]
    assert kinds == ["finish"]
    assert "расшифровать" in monitor.calls[0][1]["message"]
    assert not cache.deleted and not invalidated
