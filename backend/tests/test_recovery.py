"""Тесты восстановления зависших статусов 'processing' (B-3, неделя 2)."""

from tasks.recovery import _recover_stuck_processing_on_boot, recover_stuck_processing


class _FakeQuery:
    def __init__(self, session):
        self.session = session

    def filter(self, *a, **k):
        return self

    def update(self, values, **k):
        self.session.updates.append(values)
        return 3  # «восстановлено» 3 товара


class _FakeSession:
    def __init__(self):
        self.updates = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query(self, *a, **k):
        return _FakeQuery(self)

    def commit(self):
        self.commits += 1


def test_recover_stuck_processing_resets_to_error():
    session = _FakeSession()
    recovered = recover_stuck_processing(session_factory=lambda: session)

    assert recovered == 3
    assert session.commits == 1
    (values,) = session.updates
    assert values["status"] == "error"
    assert "Повторите миграцию" in values["error_message"]


def test_recover_stuck_processing_zero_is_ok():
    session = _FakeSession()

    class _ZeroQuery(_FakeQuery):
        def update(self, values, **k):
            self.session.updates.append(values)
            return 0

    session.query = lambda *a, **k: _ZeroQuery(session)
    assert recover_stuck_processing(session_factory=lambda: session) == 0


def test_boot_hook_skips_xlsx_worker():
    """xlsx-воркер не ставит 'processing' — рестарт его контейнера не должен
    сбрасывать чужие in-flight миграции."""

    def _factory():
        raise AssertionError("БД не должна открываться на xlsx-воркере")

    class _Sender:
        hostname = "celery@xlsx-worker-1"

    _recover_stuck_processing_on_boot(sender=_Sender())  # не должен бросить


def test_boot_hook_recovers_on_default_worker(monkeypatch):
    _FakeSession()
    monkeypatch.setattr("tasks.recovery.recover_stuck_processing", lambda: 5)

    class _Sender:
        hostname = "celery@default-worker-1"

    _recover_stuck_processing_on_boot(sender=_Sender())  # не должен бросить


def test_boot_hook_swallows_db_errors(monkeypatch):
    """Recovery — не причина падать на старте воркера."""

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("tasks.recovery.recover_stuck_processing", _boom)

    class _Sender:
        hostname = "celery@default-worker-1"

    _recover_stuck_processing_on_boot(sender=_Sender())  # не должен бросить
