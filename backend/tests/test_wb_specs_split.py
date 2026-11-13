"""Р17: гарантия, что разбиение services/wb_specs.py (313 строк) на пакет
сохранило публичный API и поведение.

Импортёр один — tasks/catalog_tasks.py: `from services.wb_specs import
refresh_wildberries_specs`. Поведение проверяем без сети: HTTP-вызовы и
зависимости оркестратора подменяем monkeypatch'ем в тех модулях, где они
используются (прецедент — test_ozon_specs_split.py).
"""

import asyncio


def test_public_api_preserved():
    import services.wb_specs as pkg
    from services.wb_specs import _characteristics, _http, _refresh, _storage, _subjects

    assert pkg.refresh_wildberries_specs is _refresh.refresh_wildberries_specs
    assert pkg.fetch_wb_subjects is _subjects.fetch_wb_subjects
    assert pkg.fetch_wb_characteristics is _characteristics.fetch_wb_characteristics
    assert pkg.fetch_wb_directory is _characteristics.fetch_wb_directory
    # константы — те же объекты, что в подмодулях
    assert pkg.WB_API_BASE is _http.WB_API_BASE
    assert pkg.WB_REQUEST_DELAY is _refresh.WB_REQUEST_DELAY
    assert pkg.PROGRESS_EVERY is _refresh.PROGRESS_EVERY
    # upsert живёт в _storage и используется оркестратором оттуда
    assert _refresh._upsert_spec is _storage._upsert_spec

    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {
        "PROGRESS_EVERY",
        "WB_API_BASE",
        "WB_REQUEST_DELAY",
        "fetch_wb_characteristics",
        "fetch_wb_directory",
        "fetch_wb_subjects",
        "refresh_wildberries_specs",
    }


def test_wb_headers_raw_token():
    from services.wb_specs._http import _wb_headers

    # WB принимает сырой токен без схемы Bearer/OAuth
    assert _wb_headers("eyWb.token") == {
        "Authorization": "eyWb.token",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """Асинхронный стаб httpx.AsyncClient: get/post по маршруту."""

    def __init__(self, routes):
        self._routes = routes

    async def get(self, url, headers=None, params=None):
        return self._routes[("GET", url)](params)

    async def post(self, url, headers=None, json=None):
        return self._routes[("POST", url)](json)


def test_fetch_wb_subjects_normalizes_items():
    from services.wb_specs._http import WB_API_BASE
    from services.wb_specs._subjects import fetch_wb_subjects

    payload = {
        "data": [
            {"objectID": 101, "object": "Футболки", "parentID": 11},
            {"id": 202, "name": "Пижамы"},  # альтернативные ключи
        ]
    }

    def route(params):
        return _FakeResponse(payload)

    client = _FakeClient({("GET", f"{WB_API_BASE}/content/v2/object/parent/all"): route})
    subjects = asyncio.run(fetch_wb_subjects(client, "wb-token"))

    assert subjects == [
        {"id": "101", "name": "Футболки", "parent_id": "11"},
        {"id": "202", "name": "Пижамы", "parent_id": None},
    ]


def test_fetch_wb_characteristics_and_directory():
    from services.wb_specs._characteristics import fetch_wb_characteristics
    from services.wb_specs._http import WB_API_BASE

    def chars_route(body):
        assert body == {"objectID": 101}
        return _FakeResponse(
            {
                "data": [
                    {
                        "id": 7,
                        "name": "Цвет",
                        "required": True,
                        "directoryID": 55,
                        "maxCount": 20,
                    },
                    {
                        "id": 8,
                        "name": "Комплектация",
                        "type": "string",
                        "required": False,
                        "maxCount": 1,
                    },
                ]
            }
        )

    def dict_route(params):
        assert params == {"limit": 1000}
        return _FakeResponse({"data": [{"value": "Красный"}, {"name": "Синий"}]})

    client = _FakeClient(
        {
            ("POST", f"{WB_API_BASE}/content/v2/object/characteristics/list"): chars_route,
            ("GET", f"{WB_API_BASE}/content/v2/directory/55"): dict_route,
        }
    )
    attrs = asyncio.run(fetch_wb_characteristics(client, "wb-token", "101"))

    # словарь подтянулся отдельным GET-запросом
    assert attrs == [
        {
            "id": "7",
            "name": "Цвет",
            "type": "multiselect",  # select + maxCount > 1
            "required": True,
            "group": "common",
            "values": ["Красный", "Синий"],
            "case_sensitive": True,
            "separator": ";",
            "unit": None,
            "allow_unit_in_value": False,
            "max_count": 20,
        },
        {
            "id": "8",
            "name": "Комплектация",
            "type": "text",
            "required": False,
            "group": "common",
            "values": None,
            "case_sensitive": True,
            "separator": ";",
            "unit": None,
            "allow_unit_in_value": False,
            "max_count": 1,
        },
    ]


def test_fetch_wb_directory_failure_returns_none():
    from services.wb_specs._characteristics import fetch_wb_directory
    from services.wb_specs._http import WB_API_BASE

    def route(params):
        return _FakeResponse({}, status_code=500)

    client = _FakeClient({("GET", f"{WB_API_BASE}/content/v2/directory/77"): route})
    assert asyncio.run(fetch_wb_directory(client, "wb-token", 77)) is None


def test_map_wb_type_heuristics():
    from services.wb_specs._characteristics import _map_wb_type

    assert _map_wb_type({"type": "number"}, 0) == "number"
    assert _map_wb_type({"type": "float"}, 0) == "number"
    assert _map_wb_type({"type": "boolean"}, 0) == "select"
    # словарь → select даже без явного типа
    assert _map_wb_type({}, 55) == "select"
    # единица измерения без типа и словаря → number
    assert _map_wb_type({"unit": "кг"}, 0) == "number"
    # иначе текст
    assert _map_wb_type({}, 0) == "text"


def test_build_validation_rules_max_values():
    from services.wb_specs._characteristics import (
        _build_special_requirements,
        _build_validation_rules,
    )

    attrs = [
        {
            "id": "7",
            "values": ["Красный", "Синий"],
            "case_sensitive": True,
            "type": "multiselect",
            "separator": ";",
            "max_count": 20,
        },
        {
            "id": "8",
            "values": None,
            "case_sensitive": True,
            "type": "text",
            "separator": ";",
            "max_count": 1,
        },
    ]
    rules = _build_validation_rules(attrs)

    assert rules["price"] == {"min": 0.01}
    assert rules["units_per_item"] == {"min": 1, "type": "integer"}
    # enum + case_sensitive + разделитель multiselect + лимит значений
    assert rules["7"]["enum"] == ["Красный", "Синий"]
    assert rules["7"]["case_sensitive"] is True
    assert rules["7"]["separator"] == ";"
    assert rules["7"]["max_values"] == 20
    # max_count > 1, но без словаря — правило только с лимитом
    assert rules["8"] == {"max_values": 1}
    # спецтребования шаблона WB
    assert _build_special_requirements() == {
        "okpd_required_for_tags": [],
        "excisable_tags": [],
    }


def test_refresh_orchestrator_pause_before_each_subject(monkeypatch):
    from services.wb_specs import _refresh

    subjects = [{"id": str(i), "name": f"Предмет-{i}", "parent_id": None} for i in range(3)]

    async def fake_subjects(client, token):
        return [dict(s) for s in subjects]

    async def fake_chars(client, token, object_id):
        return [
            {
                "id": "7",
                "name": "Цвет",
                "type": "select",
                "required": True,
                "values": ["Красный"],
                "case_sensitive": True,
                "separator": ";",
            }
        ]

    upserts = []

    def fake_upsert(user_id, platform, category_id, category_name, parent_category_id, spec):
        upserts.append((platform, category_id, category_name, spec["required_fields"]))

    monkeypatch.setattr(_refresh, "fetch_wb_subjects", fake_subjects)
    monkeypatch.setattr(_refresh, "fetch_wb_characteristics", fake_chars)
    monkeypatch.setattr(_refresh, "_upsert_spec", fake_upsert)
    monkeypatch.setattr(_refresh, "WB_REQUEST_DELAY", 0)  # не спим между предметами

    progress = []
    checks = iter([False, True])  # пауза перед вторым предметом

    done_keys = set()
    result = asyncio.run(
        _refresh.refresh_wildberries_specs(
            user_id=1,
            token="wb-token",
            progress_cb=progress.append,
            pause_check=lambda: next(checks),
            done_keys=done_keys,
        )
    )

    # первый предмет сохранён в БД, второй не начат
    assert result["paused"] is True
    assert result["fetched"] == 1
    assert result["errors"] == 0
    assert upserts == [("wildberries", "0", "Предмет-0", ["Цвет"])]
    assert done_keys == {"0"}
    assert progress[0] == {"total": 3, "fetched": 0, "errors": 0}


def test_refresh_orchestrator_full_run_with_skip_and_errors(monkeypatch):
    from services.wb_specs import _refresh

    subjects = [{"id": str(i), "name": f"Предмет-{i}", "parent_id": None} for i in range(3)]

    async def fake_subjects(client, token):
        return [dict(s) for s in subjects]

    async def fake_chars(client, token, object_id):
        if object_id == "1":
            raise RuntimeError("boom")
        return []

    upserts = []

    def fake_upsert(user_id, platform, category_id, category_name, parent_category_id, spec):
        upserts.append((category_id, category_name, spec["sheets"]))

    monkeypatch.setattr(_refresh, "fetch_wb_subjects", fake_subjects)
    monkeypatch.setattr(_refresh, "fetch_wb_characteristics", fake_chars)
    monkeypatch.setattr(_refresh, "_upsert_spec", fake_upsert)
    monkeypatch.setattr(_refresh, "WB_REQUEST_DELAY", 0)

    progress = []
    done_keys = set()
    result = asyncio.run(
        _refresh.refresh_wildberries_specs(
            user_id=1,
            token="wb-token",
            category_ids=["0", "1", "2"],
            skip_category_ids=["2"],  # уже сохранён до паузы — пропустить
            progress_cb=progress.append,
            done_keys=done_keys,
        )
    )

    assert result == {
        "platform": "wildberries",
        "fetched": 1,
        "errors": 1,
        "error_details": [{"category_id": "1", "error": "boom"}],
    }
    # упавший предмет не дошёл до upsert; выгрузка WB — один лист
    assert upserts == [("0", "Предмет-0", ["Товары"])]
    assert done_keys == {"0"}
    # финальный прогресс дошёл до колбэка
    assert progress[-1] == {"total": 2, "fetched": 1, "errors": 1}


def test_refresh_orchestrator_empty_selection(monkeypatch):
    from services.wb_specs import _refresh

    async def fake_subjects(client, token):
        return [{"id": "9", "name": "Предмет", "parent_id": None}]

    monkeypatch.setattr(_refresh, "fetch_wb_subjects", fake_subjects)

    result = asyncio.run(
        _refresh.refresh_wildberries_specs(user_id=1, token="wb-token", category_ids=["777"])
    )

    assert result == {
        "platform": "wildberries",
        "fetched": 0,
        "errors": 0,
        "error_details": [],
    }
