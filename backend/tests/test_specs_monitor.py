"""Тесты реестра загрузок спеков (пакет services/specs_monitor/) — без Redis.

FakeRedis эмулирует только те команды, которые использует specs_monitor:
pipeline(setex/sadd/srem/lpush/ltrim/expire/execute), get, smembers, mget, lrange.

После разбиения на пакет (Р9) redis_client импортирован отдельно в
_lifecycle/_pause/_queries — клиент подменяем в этих модулях (helper
_set_redis), а не на пакете; HISTORY_LEN — в _lifecycle.
"""

import json

import pytest

from services import specs_monitor


class FakePipeline:
    def __init__(self, r):
        self.r = r
        self.ops = []

    def setex(self, key, ttl, val):
        self.ops.append(("setex", key, val))
        return self

    def sadd(self, key, *vals):
        self.ops.append(("sadd", key, vals))
        return self

    def srem(self, key, *vals):
        self.ops.append(("srem", key, vals))
        return self

    def lpush(self, key, val):
        self.ops.append(("lpush", key, val))
        return self

    def ltrim(self, key, start, end):
        self.ops.append(("ltrim", key, start, end))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key))
        return self

    def execute(self):
        for op in self.ops:
            kind, key = op[0], op[1]
            if kind == "setex":
                self.r.data[key] = op[2]
            elif kind == "sadd":
                self.r.sets.setdefault(key, set()).update(op[2])
            elif kind == "srem":
                self.r.sets.setdefault(key, set()).difference_update(op[2])
            elif kind == "lpush":
                self.r.lists.setdefault(key, []).insert(0, op[2])
            elif kind == "ltrim":
                lst = self.r.lists.get(key, [])
                end = op[3] + 1 if op[3] >= 0 else len(lst) + op[3] + 1
                self.r.lists[key] = lst[op[2] : end]
        self.ops = []


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.sets = {}
        self.lists = {}

    def pipeline(self):
        return FakePipeline(self)

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, val):
        self.data[key] = val
        return self

    def delete(self, *keys):
        for k in keys:
            self.data.pop(k, None)
            self.sets.pop(k, None)

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def mget(self, keys):
        return [self.data.get(k) for k in keys]

    def lrange(self, key, start, end):
        lst = self.lists.get(key, [])
        return lst[start : end + 1] if end >= 0 else lst[start:]


def _set_redis(monkeypatch, client):
    """Подменить redis_client во всех модулях пакета, которые ходят в Redis (Р9)."""
    from services.specs_monitor import _lifecycle, _pause, _queries

    for mod in (_lifecycle, _pause, _queries):
        monkeypatch.setattr(mod, "redis_client", client)


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    _set_redis(monkeypatch, fake)
    return fake


# ==================== register / set_running / finish ====================


def test_register_then_active_listed_as_queued(fake_redis):
    specs_monitor.register("t1", platform="yandex", user_id=1, username="admin")

    active = specs_monitor.list_active()
    assert len(active) == 1
    assert active[0]["task_id"] == "t1"
    assert active[0]["state"] == "queued"
    assert active[0]["platform"] == "yandex"
    assert active[0]["username"] == "admin"
    assert active[0]["started_at"] is None


def test_set_running_updates_state_and_creates_missing_entry(fake_redis):
    # Запись не регистрировалась роутером (ручной запуск) — set_running создаёт её сам
    specs_monitor.set_running("t2", platform="ozon", user_id=5)
    active = specs_monitor.list_active()
    assert active[0]["state"] == "running"
    assert active[0]["platform"] == "ozon"
    assert active[0]["started_at"] is not None


def test_full_lifecycle_queued_running_done(fake_redis):
    specs_monitor.register("t3", platform="wildberries", user_id=2, username="bob")
    specs_monitor.set_running("t3")
    assert specs_monitor.list_active()[0]["state"] == "running"

    specs_monitor.finish("t3", status="partial", total=100, success=90, errors=10, duration_ms=5000)

    # Из активных исчезла, в истории появилась с итогом
    assert specs_monitor.list_active() == []
    history = specs_monitor.list_history()
    assert len(history) == 1
    assert history[0]["state"] == "done"
    assert history[0]["status"] == "partial"
    assert history[0]["total"] == 100
    assert history[0]["success"] == 90
    assert history[0]["errors"] == 10
    assert history[0]["duration_ms"] == 5000
    # Ключ задачи сохраняет итоговые поля
    info = json.loads(fake_redis.data["specs:task:t3"])
    assert info["state"] == "done"
    assert info["username"] == "bob"  # из register, не потерялся


def test_history_trimmed_to_limit(fake_redis, monkeypatch):
    # HISTORY_LEN читает finish() — после Р9 константа живёт в _lifecycle
    from services.specs_monitor import _lifecycle

    monkeypatch.setattr(_lifecycle, "HISTORY_LEN", 3)
    for i in range(5):
        specs_monitor.register(f"t{i}", platform="ozon", user_id=1)
        specs_monitor.finish(f"t{i}", status="success", total=1, success=1)

    history = specs_monitor.list_history()
    assert len(history) == 3
    # Свежие сверху: последняя завершённая — t4
    assert history[0]["task_id"] == "t4"


def test_list_active_skips_expired_keys(fake_redis):
    # Ключ задачи протух (TTL), но id остался в SET active — не должен ломать список
    specs_monitor.register("gone", platform="ozon", user_id=1)
    specs_monitor.register("alive", platform="ozon", user_id=1)
    del fake_redis.data["specs:task:gone"]

    active = specs_monitor.list_active()
    assert [t["task_id"] for t in active] == ["alive"]


def test_list_active_ordered_newest_first(fake_redis):
    for i, ts in enumerate([100.0, 300.0, 200.0]):
        specs_monitor.register(f"t{i}", platform="ozon", user_id=1)
        # подменяем enqueued_at для детерминированного порядка
        info = json.loads(fake_redis.data[f"specs:task:t{i}"])
        info["enqueued_at"] = ts
        fake_redis.data[f"specs:task:t{i}"] = json.dumps(info)

    assert [t["task_id"] for t in specs_monitor.list_active()] == ["t1", "t2", "t0"]


# ==================== is_stale ====================


def test_is_stale_running_long_without_progress(fake_redis, monkeypatch):
    specs_monitor.register("s1", platform="ozon", user_id=1)
    specs_monitor.set_running("s1")
    info = specs_monitor.list_active()[0]
    # подменяем started_at в прошлое
    monkeyed = dict(info, started_at=info["started_at"] - 3600)
    assert specs_monitor.is_stale(monkeyed, live_percent=0) is True
    # с прогрессом — не протухла
    assert specs_monitor.is_stale(monkeyed, live_percent=42) is False


def test_is_stale_false_for_queued_and_recent(fake_redis, monkeypatch):
    specs_monitor.register("s2", platform="ozon", user_id=1)
    queued = specs_monitor.list_active()[0]
    assert specs_monitor.is_stale(queued) is False  # queued не проверяется

    specs_monitor.set_running("s2")
    running = specs_monitor.list_active()[0]
    assert specs_monitor.is_stale(running) is False  # только что стартовала


# ==================== graceful degradation без Redis ====================


def test_all_noop_without_redis(monkeypatch):
    _set_redis(monkeypatch, None)
    specs_monitor.register("x", platform="ozon", user_id=1)
    specs_monitor.set_running("x")
    specs_monitor.finish("x", status="success")
    assert specs_monitor.list_active() == []
    assert specs_monitor.list_history() == []


# ==================== пауза / возобновление ====================


def test_request_pause_marks_info_and_sets_flag(fake_redis):
    specs_monitor.register("p1", platform="ozon", user_id=1, username="admin")

    assert specs_monitor.request_pause("p1") is True

    # флаг виден задаче (проверка между блоками / на старте)
    assert specs_monitor.pause_requested("p1") is True
    # в инфо появился признак для UI («останавливается…»)
    info = specs_monitor.get_info("p1")
    assert info["pause_requested"] is True
    # повторный запрос паузы безвреден
    assert specs_monitor.request_pause("p1") is True


def test_request_pause_false_for_missing_or_done(fake_redis):
    assert specs_monitor.request_pause("ghost") is False

    specs_monitor.register("p2", platform="ozon", user_id=1)
    specs_monitor.finish("p2", status="success")
    assert specs_monitor.request_pause("p2") is False
    assert specs_monitor.pause_requested("p2") is False


def test_clear_pause_removes_flag(fake_redis):
    specs_monitor.register("p3", platform="ozon", user_id=1)
    specs_monitor.request_pause("p3")
    specs_monitor.clear_pause("p3")
    assert specs_monitor.pause_requested("p3") is False


def test_finish_paused_saves_done_keys(fake_redis):
    specs_monitor.register("p4", platform="yandex", user_id=1, username="admin")
    specs_monitor.set_running("p4")

    specs_monitor.finish(
        "p4",
        status="paused",
        total=70,
        success=70,
        duration_ms=1234,
        done_keys=["91491", "91492"],
    )

    assert specs_monitor.list_active() == []
    history = specs_monitor.list_history()
    assert history[0]["status"] == "paused"
    assert history[0]["done_keys"] == ["91491", "91492"]
    # счётчики сохранены — resume покажет, сколько уже сделано
    assert history[0]["success"] == 70
    # флаг паузы сброшен сам (finish — терминальное состояние)
    assert specs_monitor.get_info("p4")["pause_requested"] is False


def test_resume_params_saved_and_readable(fake_redis):
    specs_monitor.register(
        "r1",
        platform="ozon",
        user_id=7,
        username="admin",
        resume_params={
            "enc_key": "enc1:deadbeef",
            "category_ids": ["17027447"],
            "business_id": None,
            "skip_category_ids": [],
        },
    )

    info = specs_monitor.get_info("r1")
    assert info["resume_params"]["enc_key"] == "enc1:deadbeef"
    assert info["resume_params"]["category_ids"] == ["17027447"]
    # set_running не должен потерять параметры возобновления
    specs_monitor.set_running("r1")
    assert specs_monitor.get_info("r1")["resume_params"]["enc_key"] == "enc1:deadbeef"


def test_mark_resumed_decorates_history_and_blocks_repeat(fake_redis):
    specs_monitor.register("r2", platform="ozon", user_id=1)
    specs_monitor.finish("r2", status="paused", done_keys=["a", "b"])

    # до продолжения — resume возможен
    assert specs_monitor.get_resumed("r2") is None

    specs_monitor.mark_resumed("r2", "new-task-id")
    assert specs_monitor.get_resumed("r2") == "new-task-id"

    # история показывает, что задача уже продолжена
    history = specs_monitor.list_history()
    assert history[0]["resumed_as"] == "new-task-id"


def test_pause_funcs_noop_without_redis(monkeypatch):
    _set_redis(monkeypatch, None)
    assert specs_monitor.request_pause("x") is False
    assert specs_monitor.pause_requested("x") is False
    specs_monitor.clear_pause("x")  # не падает
    assert specs_monitor.get_info("x") is None
    specs_monitor.mark_resumed("x", "y")  # не падает
    assert specs_monitor.get_resumed("x") is None


# ==================== sync_done_keys (прогресс для resume при гибели воркера) ====================


def test_sync_done_keys_updates_running_entry(fake_redis):
    specs_monitor.register("k1", platform="ozon", user_id=1)
    specs_monitor.set_running("k1")

    specs_monitor.sync_done_keys("k1", ["100_1", "200_3"])

    info = specs_monitor.get_info("k1")
    assert info["done_keys"] == ["100_1", "200_3"]
    assert info["state"] == "running"  # состояние не тронуто


def test_sync_done_keys_ignored_for_done_or_missing(fake_redis):
    specs_monitor.register("k2", platform="ozon", user_id=1)
    specs_monitor.finish("k2", status="paused", done_keys=["a"])

    # терминальная запись — прогресс не перезатирается
    specs_monitor.sync_done_keys("k2", ["b"])
    assert specs_monitor.get_info("k2")["done_keys"] == ["a"]

    # несуществующая задача — не создаётся
    specs_monitor.sync_done_keys("ghost", ["x"])
    assert specs_monitor.get_info("ghost") is None


def test_sync_done_keys_noop_without_redis(monkeypatch):
    _set_redis(monkeypatch, None)
    specs_monitor.sync_done_keys("x", ["a"])  # не падает


# ==================== reconcile_on_startup (жёсткий перезапуск воркера) ====================


def test_reconcile_marks_running_interrupted_and_keeps_queued(fake_redis):
    # running — убита вместе с воркером, queued — сообщение может лежать в брокере
    specs_monitor.register("q1", platform="yandex", user_id=1)
    specs_monitor.register("run1", platform="ozon", user_id=2)
    specs_monitor.set_running("run1")
    specs_monitor.sync_done_keys("run1", ["10_7", "11_7"])

    closed = specs_monitor.reconcile_on_startup()

    assert closed == 1
    active = specs_monitor.list_active()
    assert [t["task_id"] for t in active] == ["q1"]  # queued не тронута
    assert active[0]["state"] == "queued"

    history = specs_monitor.list_history()
    assert len(history) == 1
    assert history[0]["status"] == "interrupted"
    # прогресс сохранён — resume продолжит с него, а не с нуля
    assert specs_monitor.get_info("run1")["done_keys"] == ["10_7", "11_7"]


def test_reconcile_writes_last_live_progress(fake_redis):
    specs_monitor.register("run2", platform="ozon", user_id=1)
    specs_monitor.set_running("run2")

    def fake_live(task_id):
        return {"total": 8347, "success": 340, "errors": 0}

    specs_monitor.reconcile_on_startup(live=fake_live)

    history = specs_monitor.list_history()
    assert history[0]["status"] == "interrupted"
    assert history[0]["total"] == 8347
    assert history[0]["success"] == 340


def test_reconcile_clears_hung_pause_flag(fake_redis):
    specs_monitor.register("run3", platform="ozon", user_id=1)
    specs_monitor.set_running("run3")
    specs_monitor.request_pause("run3")  # пауза запрошена, но воркер умер

    specs_monitor.reconcile_on_startup()

    assert specs_monitor.pause_requested("run3") is False
    assert specs_monitor.list_active() == []


def test_reconcile_noop_without_redis(monkeypatch):
    _set_redis(monkeypatch, None)
    assert specs_monitor.reconcile_on_startup() == 0  # не падает


# ==================== маршрутизация очередей ====================


def test_specs_task_routed_to_dedicated_queue():
    # Спеки — 30+ минут в solo-пуле: раньше они стояли в общей очереди default
    # и миграции «зависали на 0%» за ними. Теперь у спеков своя очередь.
    from celery_app import celery_app

    route = celery_app.conf.task_routes.get("tasks.refresh_specs_task")
    assert route and route.get("queue") == "specs"
    assert route.get("routing_key") == "specs"
    # миграции остаются в default — их больше ничего не блокирует
    assert "tasks.migrate_product_task" not in celery_app.conf.task_routes


def test_resumable_statuses_include_interrupted():
    # «на паузе» (админ остановил) и «прервана» (воркер перезапущен) — продолжаемы
    assert specs_monitor.RESUMABLE_STATUSES == ("paused", "interrupted")
