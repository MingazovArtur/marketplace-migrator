"""Р9: гарантия, что разбиение services/specs_monitor.py (419 строк) на пакет
сохранило публичный API.

Импортёры (routers/categories/, tasks/catalog_tasks.py) используют
`from services import specs_monitor` и атрибутный доступ — все имена должны
остаться на пакете теми же объектами, что в подмодулях. Поведение реестра
(без Redis, на FakeRedis) покрыто tests/test_specs_monitor.py.
"""


def test_public_api_preserved():
    import services.specs_monitor as pkg
    from services.specs_monitor import _lifecycle, _pause, _queries

    assert pkg.register is _lifecycle.register
    assert pkg.set_running is _lifecycle.set_running
    assert pkg.finish is _lifecycle.finish
    assert pkg.get_info is _lifecycle.get_info
    assert pkg.sync_done_keys is _lifecycle.sync_done_keys
    assert pkg.reconcile_on_startup is _lifecycle.reconcile_on_startup
    assert pkg.request_pause is _pause.request_pause
    assert pkg.pause_requested is _pause.pause_requested
    assert pkg.clear_pause is _pause.clear_pause
    assert pkg.mark_resumed is _pause.mark_resumed
    assert pkg.get_resumed is _pause.get_resumed
    assert pkg.list_active is _queries.list_active
    assert pkg.list_history is _queries.list_history
    assert pkg.is_stale is _queries.is_stale
    assert pkg.RESUMABLE_STATUSES == ("paused", "interrupted")

    # на пакете нет случайных публичных имён
    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {
        "RESUMABLE_STATUSES",
        "register",
        "set_running",
        "finish",
        "get_info",
        "sync_done_keys",
        "reconcile_on_startup",
        "request_pause",
        "pause_requested",
        "clear_pause",
        "mark_resumed",
        "get_resumed",
        "list_active",
        "list_history",
        "is_stale",
    }


def test_redis_client_patch_points():
    """redis_client импортирован на уровне модуля в каждом файле пакета,
    который ходит в Redis, — тесты подменяют именно эти привязки
    (helper _set_redis в test_specs_monitor.py), а не пакет."""
    from services import cache_service
    from services.specs_monitor import _lifecycle, _pause, _queries

    for mod in (_lifecycle, _pause, _queries):
        assert mod.redis_client is cache_service.redis_client


def test_key_helpers():
    from services.specs_monitor import _keys

    assert _keys._task_key("abc") == "specs:task:abc"
    assert _keys._pause_key("abc") == "specs:pause:abc"
    assert _keys._resumed_key("abc") == "specs:resumed:abc"
    assert _keys.ACTIVE_KEY == "specs:tasks:active"
    assert _keys.HISTORY_KEY == "specs:tasks:history"

    assert _keys._load('{"a": 1}') == {"a": 1}
    assert _keys._load("not-json") is None
    assert _keys._load(None) is None
    assert _keys._load('["list"]') is None  # не dict — не запись задачи
    assert _keys._dump({"a": "ы"}) == '{"a": "ы"}'  # ensure_ascii=False


def test_is_stale_thresholds():
    """running без прогресса: свежая — жива, старее STALE_RUNNING_SEC — зависла."""
    from services.specs_monitor import _keys, _queries

    fresh = {"state": "running", "started_at": _keys._now() - 60}
    assert _queries.is_stale(fresh, live_percent=0) is False

    hung = {"state": "running", "started_at": _keys._now() - _keys.STALE_RUNNING_SEC - 1}
    assert _queries.is_stale(hung, live_percent=0) is True
    assert _queries.is_stale(hung, live_percent=5) is False  # есть живой прогресс

    # queued/done не проверяются вовсе
    assert _queries.is_stale({"state": "queued"}, live_percent=0) is False
    assert _queries.is_stale({"state": "done"}, live_percent=0) is False
    assert _queries.is_stale("not-a-dict") is False
