"""Р15: гарантия, что разбиение tasks/migrate_tasks.py (529 строк) на пакет
сохранило публичный API и поведение.

Импортёр один — tasks/__init__.py: `from tasks.migrate_tasks import
migrate_batch_task, migrate_product_task` (не менялся). Имена Celery-задач
заданы явно (name="tasks.*") и не зависят от пути модуля: регистрация задач
и маршрутизация очередей (celery_app.py: include=["tasks"]) стабильны.

Поведение проверяем без брокера: зависимости подменяем в подмодулях, где
они используются (прецедент — test_specs_monitor.py), задачу выполняем
eager-вызовом .apply(throw=True).
"""

import types

import pytest

import tasks.migrate_tasks as pkg
import tasks.migrate_tasks._batch as batch_mod
import tasks.migrate_tasks._notify as notify_mod
import tasks.migrate_tasks._single as single_mod


def test_public_api_preserved():
    from tasks.migrate_tasks._batch import migrate_batch_task as from_batch
    from tasks.migrate_tasks._single import migrate_product_task as from_single

    assert pkg.migrate_product_task is from_single
    assert pkg.migrate_batch_task is from_batch
    # имена пакета — только публичный API, без случайных имён
    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {"migrate_product_task", "migrate_batch_task"}


def test_tasks_reexport_same_object():
    # from tasks import ... — тот же объект (импортёр tasks/__init__.py не менялся)
    from tasks import migrate_batch_task, migrate_product_task

    assert migrate_product_task is pkg.migrate_product_task
    assert migrate_batch_task is pkg.migrate_batch_task


def test_celery_task_names_explicit():
    # явные имена задач — маршрутизация очередей celery_app.py не зависит
    # от пути модуля (правило engineering.md); ровно как в монолите
    assert single_mod.migrate_product_task.name == "tasks.migrate_product_task"
    assert batch_mod.migrate_batch_task.name == "tasks.migrate_batch_task"


def test_task_registration_on_celery_app():
    from celery_app import celery_app

    # задачи зарегистрированы под явными именами (декоратор сработал при импорте);
    # registry хранит резолвнутый объект, а декоратор возвращает PromiseProxy,
    # поэтому сверяем имя и исходную функцию, а не identity
    registered = celery_app.tasks["tasks.migrate_product_task"]
    assert registered.name == "tasks.migrate_product_task"
    assert registered.run.__module__ == "tasks.migrate_tasks._single"
    assert celery_app.tasks["tasks.migrate_batch_task"].name == "tasks.migrate_batch_task"
    assert celery_app.tasks["tasks.migrate_batch_task"].run.__module__ == "tasks.migrate_tasks._batch"
    assert pkg.migrate_product_task.name == registered.name


# ---------------------------------------------------------------------------
# _notify_batch_done (v5): письмо о завершении пакета
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, *, email, verified, notify=True, username="Вася"):
        self.email = email
        self.email_verified_at = "2026-01-01" if verified else None
        self.notify_batch_done = notify
        self.username = username


class _FakeSession:
    def __init__(self, user):
        self.user = user

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, model, user_id):
        return self.user


@pytest.fixture()
def notify_deps(monkeypatch):
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs)

    import services.email_service as email_svc

    monkeypatch.setattr(email_svc, "send_batch_migration_email_sync", fake_send)
    return sent


def _set_user(monkeypatch, user):
    monkeypatch.setattr(notify_mod, "SessionLocal", lambda: _FakeSession(user))


def test_notify_skips_unverified_email(notify_deps, monkeypatch):
    _set_user(monkeypatch, _FakeUser(email="u@x.ru", verified=False))
    notify_mod._notify_batch_done(7, "ozon", 10, 8, 2, 500, [])
    assert notify_deps == []


def test_notify_skips_disabled_preference(notify_deps, monkeypatch):
    _set_user(monkeypatch, _FakeUser(email="u@x.ru", verified=True, notify=False))
    notify_mod._notify_batch_done(7, "ozon", 10, 8, 2, 500, [])
    assert notify_deps == []


def test_notify_skips_missing_user(notify_deps, monkeypatch):
    _set_user(monkeypatch, None)
    notify_mod._notify_batch_done(7, "ozon", 10, 8, 2, 500, [])
    assert notify_deps == []


def test_notify_sends_to_verified(notify_deps, monkeypatch):
    _set_user(monkeypatch, _FakeUser(email="u@x.ru", verified=True, notify=True))
    errors = [{"id": 1, "error": f"e{i}"} for i in range(8)]
    notify_mod._notify_batch_done(7, "wildberries", 10, 8, 2, 500, errors)

    assert len(notify_deps) == 1
    sent = notify_deps[0]
    assert sent["to_email"] == "u@x.ru"
    assert sent["username"] == "Вася"
    # имя платформы подставляется из PLATFORM_CONFIG
    assert sent["platform_name"] != "wildberries"
    assert sent["total"] == 10 and sent["success"] == 8 and sent["errors"] == 2
    # сэмпл ошибок — первые 5
    assert len(sent["error_sample"]) == 5
    assert sent["error_sample"][0]["error"] == "e0"


def test_notify_unknown_platform_falls_back(notify_deps, monkeypatch):
    _set_user(monkeypatch, _FakeUser(email="u@x.ru", verified=True))
    notify_mod._notify_batch_done(7, "unknown_p", 1, 1, 0, 5, [])
    assert notify_deps[0]["platform_name"] == "unknown_p"


def test_notify_send_error_does_not_raise(notify_deps, monkeypatch):
    _set_user(monkeypatch, _FakeUser(email="u@x.ru", verified=True))

    import services.email_service as email_svc

    def boom(**kwargs):
        raise RuntimeError("SMTP недоступен")

    monkeypatch.setattr(email_svc, "send_batch_migration_email_sync", boom)
    # не должно упасть — ошибка отправки только логируется
    notify_mod._notify_batch_done(7, "ozon", 1, 1, 0, 5, [])


# ---------------------------------------------------------------------------
# migrate_product_task: сценарии без брокера (eager .apply)
# ---------------------------------------------------------------------------


class _RepoStub:
    """Журнал вызовов вместо репозитория (подменяется в _single)."""

    def __init__(self, products):
        self.products = products
        self.updates = []

    def get_by_id(self, product_id, user_id=None):
        return self.products.get(product_id)

    def update(self, product_id, data, user_id=None):
        self.updates.append((product_id, data))
        return True


def _patch_single(monkeypatch, products, *, category=("Одежда / Футболки", "spec"), defaults=None):
    repo = _RepoStub(products)
    stats = types.SimpleNamespace(record=types.SimpleNamespace(side_effect=None))
    recorded = []
    stats.record = lambda **kw: recorded.append(kw)
    logged = []
    op_log = types.SimpleNamespace(
        log_migration=lambda **kw: logged.append(kw),
    )
    monkeypatch.setattr(single_mod, "repo", repo)
    monkeypatch.setattr(single_mod, "stats_repo", stats)
    monkeypatch.setattr(single_mod, "op_log", op_log)
    monkeypatch.setattr(single_mod, "defaults_service", types.SimpleNamespace(
        build_updates_for_product=lambda p, u: dict(defaults or {})
    ))
    monkeypatch.setattr(
        single_mod, "_pick_target_category", lambda *a, **k: category
    )
    ensured = []
    monkeypatch.setattr(
        single_mod,
        "_ensure_canonical_attributes",
        lambda **kw: ensured.append(kw),
    )
    return repo, recorded, logged, ensured


def _product(product_id=1, **over):
    p = {
        "id": product_id,
        "name": "Футболка",
        "source": "Магнит Маркет (Файл)",
        "price": 1000.0,
        "status": "pending",
        "category": "Футболки",
        "mapped_category": None,
        "okpd_code": "14.13.10",
    }
    p.update(over)
    return p


def test_single_task_product_not_found(monkeypatch):
    _patch_single(monkeypatch, products={})
    res = single_mod.migrate_product_task.apply(
        args=(999, "ozon", 7), throw=True
    ).get()
    assert res == {"status": "error", "message": "Товар не найден или не принадлежит вам"}


def test_single_task_zero_price_rejected(monkeypatch):
    repo, _, logged, _ = _patch_single(
        monkeypatch, products={1: _product(price=0)}
    )
    res = single_mod.migrate_product_task.apply(
        args=(1, "ozon", 7), throw=True
    ).get()
    assert res["status"] == "error"
    assert "Цена товара = 0" in res["message"]
    # статус ошибки записан
    assert repo.updates[-1][1]["status"] == "error"
    # журнал миграций не пишется для отклонённого по цене
    assert logged == []


def test_single_task_no_category_rejected(monkeypatch):
    repo, _, _, _ = _patch_single(
        monkeypatch, products={1: _product(mapped_category="Старая кат.")},
        category=(None, "spec"),
    )
    res = single_mod.migrate_product_task.apply(
        args=(1, "ozon", 7), throw=True
    ).get()
    assert res["status"] == "error"
    assert "Не найдена точная категория" in res["message"]
    # прежняя категория сохраняется, не сбрасывается
    last = repo.updates[-1][1]
    assert last["mapped_category"] == "Старая кат."
    assert last["status"] == "error"


def test_single_task_success_flow(monkeypatch):
    repo, recorded, logged, ensured = _patch_single(
        monkeypatch, products={1: _product(price=1000.0)}
    )
    monkeypatch.setattr(single_mod, "PRICE_RULES", {"ozon": 1.5})
    monkeypatch.setattr(
        single_mod, "PLATFORM_CONFIG", {"ozon": {"name": "Ozon"}}
    )

    res = single_mod.migrate_product_task.apply(
        args=(1, "ozon", 7), throw=True
    ).get()

    assert res == {"status": "completed", "product_id": 1}
    final = repo.updates[-1][1]
    assert final["status"] == "success"
    assert final["price"] == 1500.0            # 1000 × 1.5 (PRICE_RULES)
    assert final["source"] == "Магнит Маркет (Файл) → Ozon"
    assert final["mapped_category"] == "Одежда / Футболки"
    # канонические атрибуты дозаполнены ДО финального статуса
    assert ensured and ensured[0]["target_platform"] == "ozon"
    # статистика и журнал — по одному успеху
    assert recorded[0]["status"] == "success" and recorded[0]["total_items"] == 1
    assert logged[0]["old_price"] == 1000.0 and logged[0]["new_price"] == 1500.0
    assert logged[0]["is_batch"] is False


def test_single_task_edited_price_overrides(monkeypatch):
    repo, _, _, _ = _patch_single(monkeypatch, products={1: _product(price=1000.0)})
    monkeypatch.setattr(single_mod, "PRICE_RULES", {"ozon": 2.0})

    res = single_mod.migrate_product_task.apply(
        args=(1, "ozon", 7, {"price": 50.0, "name": "Новое имя"}),
        throw=True,
    ).get()

    assert res["status"] == "completed"
    final = repo.updates[-1][1]
    assert final["price"] == 100.0            # отредактированная 50 × 2.0
    assert final["name"] == "Новое имя"


def test_single_task_exception_returns_error(monkeypatch):
    class _BoomRepo(_RepoStub):
        def update(self, product_id, data, user_id=None):
            raise RuntimeError("БД упала")

    monkeypatch.setattr(single_mod, "repo", _BoomRepo({1: _product()}))
    recorded = []
    monkeypatch.setattr(single_mod, "stats_repo", types.SimpleNamespace(
        record=lambda **kw: recorded.append(kw)
    ))
    monkeypatch.setattr(single_mod, "op_log", types.SimpleNamespace(
        log_migration=lambda **kw: None
    ))

    res = single_mod.migrate_product_task.apply(
        args=(1, "ozon", 7), throw=True
    ).get()
    assert res["status"] == "error"
    assert "БД упала" in res["message"]
    # suppress-ветки не роняют: ошибочная статистика тоже записана
    assert recorded[0]["status"] == "error"


# ---------------------------------------------------------------------------
# migrate_batch_task: сценарии без брокера (eager .apply)
# ---------------------------------------------------------------------------


class _BatchRepoStub:
    """Стаб repo для пакетной задачи: bulk_update/get_by_ids/update_batch."""

    def __init__(self, products):
        self.products = products
        self.bulk_updates = []
        self.batches = []

    def bulk_update(self, product_ids, data, user_id=None):
        self.bulk_updates.append((list(product_ids), data))

    def get_by_ids(self, user_id, product_ids):
        return {pid: self.products[pid] for pid in product_ids if pid in self.products}

    def update_batch(self, updates, user_id=None):
        self.batches.append(updates)
        return len(updates)


def _patch_batch(monkeypatch, products, *, category=("Одежда / Футболки", "spec")):
    repo = _BatchRepoStub(products)
    recorded = []
    monkeypatch.setattr(batch_mod, "repo", repo)
    monkeypatch.setattr(batch_mod, "stats_repo", types.SimpleNamespace(
        record=lambda **kw: recorded.append(kw)
    ))
    log_chunks = []
    monkeypatch.setattr(batch_mod, "op_log", types.SimpleNamespace(
        log_migration_batch=lambda chunk: log_chunks.append(chunk)
    ))
    monkeypatch.setattr(batch_mod, "defaults_service", types.SimpleNamespace(
        build_updates_for_product=lambda p, u: {}
    ))
    monkeypatch.setattr(batch_mod, "_pick_target_category", lambda *a, **k: category)
    monkeypatch.setattr(batch_mod, "_ensure_canonical_attributes", lambda **kw: None)
    notified = []
    monkeypatch.setattr(
        batch_mod, "_notify_batch_done", lambda **kw: notified.append(kw)
    )
    return repo, recorded, log_chunks, notified


def test_batch_task_empty_package(monkeypatch):
    repo, recorded, log_chunks, notified = _patch_batch(monkeypatch, products={})
    res = batch_mod.migrate_batch_task.apply(
        args=([], "ozon", 7), throw=True
    ).get()

    assert res["status"] == "completed"
    assert res["total"] == 0 and res["success"] == 0 and res["errors"] == 0
    assert res["percent"] == 100
    # пустой пакет не апдейтится повторно, но processing-метка ставится
    assert repo.bulk_updates == [([], {"status": "processing", "error_message": None})]
    assert log_chunks == []
    assert recorded[0]["status"] == "success"      # error_count == 0 → success
    assert notified[0]["total"] == 0


def test_batch_task_mixed_package(monkeypatch):
    repo, recorded, log_chunks, notified = _patch_batch(
        monkeypatch,
        products={
            1: _product(product_id=1, price=1000.0),
            2: _product(product_id=2, price=0.0),
            3: _product(product_id=3, price=500.0, source="X → Y → Y"),
        },
    )
    monkeypatch.setattr(batch_mod, "PRICE_RULES", {"ozon": 1.0})
    monkeypatch.setattr(batch_mod, "PLATFORM_CONFIG", {"ozon": {"name": "Ozon"}})

    res = batch_mod.migrate_batch_task.apply(
        args=([1, 2, 3], "ozon", 7), throw=True
    ).get()

    assert res["status"] == "completed"
    assert res["total"] == 3
    assert res["success"] == 2
    assert res["errors"] == 1

    # processing — один bulk-запрос на весь пакет
    assert repo.bulk_updates == [([1, 2, 3], {"status": "processing", "error_message": None})]

    # финальные статусы — ОДНИМ update_batch (P-3)
    assert len(repo.batches) == 1
    updates = dict((pid, data) for pid, data in repo.batches[0])
    assert updates[1]["status"] == "success"
    assert updates[1]["price"] == 1000.0
    assert updates[1]["source"] == "Магнит Маркет (Файл) → Ozon"
    assert updates[3]["status"] == "success"
    # защита от накопления цепочки «A → B → B»
    assert updates[3]["source"] == "X → Ozon"
    assert updates[2]["status"] == "error"
    assert "Цена = 0" in updates[2]["error_message"]

    # журнал миграций — один bulk-чанк: успех ×2 (товар с ценой 0 идёт через
    # continue БЕЗ записи в журнал — как в монолите)
    assert len(log_chunks) == 1 and len(log_chunks[0]) == 2
    statuses = {e["product_id"]: e["status"] for e in log_chunks[0]}
    assert statuses == {1: "success", 3: "success"}
    assert all(e["is_batch"] is True for e in log_chunks[0])

    # статистика: частичный успех
    assert recorded[0]["status"] == "partial"
    assert recorded[0]["success_items"] == 2 and recorded[0]["failed_items"] == 1
    # уведомление ушло с итогами пакета
    assert notified[0]["success_count"] == 2 and notified[0]["error_count"] == 1


def test_batch_task_unknown_product_counted_as_error(monkeypatch):
    repo, recorded, log_chunks, notified = _patch_batch(
        monkeypatch, products={1: _product(product_id=1, price=100.0)}
    )
    res = batch_mod.migrate_batch_task.apply(
        args=([1, 99], "ozon", 7), throw=True
    ).get()

    assert res["success"] == 1
    assert res["errors"] == 1
    assert res["error_details"][0] == {
        "id": 99,
        "error": "Товар не найден или не принадлежит вам",
    }
    # отсутствующий товар не попадает ни в статусы, ни в журнал
    assert [pid for pid, _ in repo.batches[0]] == [1]
    assert len(log_chunks[0]) == 1
