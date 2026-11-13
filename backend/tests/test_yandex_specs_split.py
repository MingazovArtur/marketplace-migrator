"""Р16: гарантия, что разбиение services/yandex_specs.py (443 строки) на пакет
сохранило публичный API и поведение.

Импортёр один — tasks/catalog_tasks.py: `from services.yandex_specs import
refresh_yandex_specs`. Поведение проверяем без сети: HTTP-слой (_post_ym) и
зависимости оркестратора подменяем monkeypatch'ем в тех модулях, где они
используются (прецедент — test_ozon_specs_split.py).
"""

import asyncio

import pytest


def test_public_api_preserved():
    import services.yandex_specs as pkg
    from services.yandex_specs import _http, _parameters, _refresh, _storage, _tree

    assert pkg.refresh_yandex_specs is _refresh.refresh_yandex_specs
    assert pkg.fetch_yandex_categories_tree is _tree.fetch_yandex_categories_tree
    assert pkg.fetch_yandex_category_parameters is _parameters.fetch_yandex_category_parameters
    # константы — те же объекты, что в подмодулях
    assert pkg.YANDEX_API_BASE is _http.YANDEX_API_BASE
    assert pkg.CONCURRENCY is _http.CONCURRENCY
    assert pkg.TIMEOUT is _http.TIMEOUT
    assert pkg.MAX_RETRIES is _http.MAX_RETRIES
    assert pkg.MAX_VALUES_PER_ATTR is _parameters.MAX_VALUES_PER_ATTR
    assert pkg.YM_BASE_REQUIRED_FIELDS is _parameters.YM_BASE_REQUIRED_FIELDS
    assert pkg.DB_CHUNK is _storage.DB_CHUNK
    assert pkg.PROGRESS_EVERY is _refresh.PROGRESS_EVERY

    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {
        "CONCURRENCY",
        "DB_CHUNK",
        "MAX_RETRIES",
        "MAX_VALUES_PER_ATTR",
        "PROGRESS_EVERY",
        "TIMEOUT",
        "YANDEX_API_BASE",
        "YM_BASE_REQUIRED_FIELDS",
        "fetch_yandex_categories_tree",
        "fetch_yandex_category_parameters",
        "refresh_yandex_specs",
    }


def test_ym_headers_token_variants():
    from services.yandex_specs._http import _ym_headers

    # современный ключ ACMA — заголовок Api-Key
    assert _ym_headers("ACMA:aaa.bbb")["Api-Key"] == "ACMA:aaa.bbb"
    # старый OAuth-токен — Authorization: OAuth
    assert _ym_headers("y0_AgAAA")["Authorization"] == "OAuth y0_AgAAA"
    # явный префикс 'OAuth ' срезается, пробелы по краям игнорируются
    h = _ym_headers("  OAuth y0_token  ")
    assert h["Authorization"] == "OAuth y0_token"
    # пустой токен не падает — уходит сырым в Api-Key
    assert _ym_headers("")["Api-Key"] == ""


def test_fetch_tree_collects_leaf_categories(monkeypatch):
    from services.yandex_specs import _tree

    payload = {
        "result": {
            "id": "1",
            "name": "Все товары",
            "children": [
                {
                    "id": "100",
                    "name": "Электроника",
                    "children": [
                        {"id": "91491", "name": "Мобильные телефоны"},
                        {"id": "", "name": "Скрытый без id"},  # нет id → skip
                    ],
                },
                {"id": "200", "name": "Лист верхнего уровня"},
            ],
        }
    }

    async def fake_post(client, sem, path, body, headers):
        assert path == "/categories/tree"
        assert body == {"language": "RU"}
        return payload

    monkeypatch.setattr(_tree, "_post_ym", fake_post)

    leaves = asyncio.run(_tree.fetch_yandex_categories_tree(None, None, {}))

    # корень 'Все товары' не попадает в full_name; пустой id отброшен
    assert leaves == [
        {
            "id": "91491",
            "name": "Мобильные телефоны",
            "full_name": "Электроника / Мобильные телефоны",
            "parent_id": "100",
        },
        {
            "id": "200",
            "name": "Лист верхнего уровня",
            "full_name": "Лист верхнего уровня",
            "parent_id": "1",
        },
    ]


def test_map_yandex_type_and_group():
    from services.yandex_specs._parameters import _map_yandex_group, _map_yandex_type

    # числовые типы
    assert _map_yandex_type("NUMERIC", False, False) == "number"
    assert _map_yandex_type("decimal", False, False) == "number"
    # словарь без multivalue → select, с multivalue → multiselect
    assert _map_yandex_type(None, True, False) == "select"
    assert _map_yandex_type("ENUM", True, True) == "multiselect"
    assert _map_yandex_type("BOOLEAN", False, False) == "select"
    # без словаря и без типа — текст
    assert _map_yandex_type(None, False, False) == "text"

    # группы: бренд → brand, вариантные слова → variant, прочее → common
    assert _map_yandex_group("Бренд") == "brand"
    assert _map_yandex_group("Производитель") == "brand"
    assert _map_yandex_group("Цвет товара") == "variant"
    assert _map_yandex_group("Размер") == "variant"
    assert _map_yandex_group("Материал") == "common"


def test_fetch_category_parameters_extracts_values_and_units(monkeypatch):
    from services.yandex_specs import _parameters

    payload = {
        "result": {
            "parameters": [
                {
                    "id": 10,
                    "name": "Цвет",
                    "type": "ENUM",
                    "required": True,
                    "values": [{"value": "Красный"}, {"value": "Синий"}, {"value": ""}],
                },
                {"id": 11, "name": "Вес", "type": "NUMERIC", "unit": {"fullName": "килограмм"}},
                {"id": 0, "name": "Без id"},  # нет id → skip
                {"id": 12, "name": None},  # нет имени → skip
            ]
        }
    }

    async def fake_post(client, sem, path, body, headers):
        assert path == "/category/91491/parameters"
        return payload

    monkeypatch.setattr(_parameters, "_post_ym", fake_post)

    attrs = asyncio.run(_parameters.fetch_yandex_category_parameters(None, None, {}, "91491"))

    assert attrs == [
        {
            "id": "10",
            "name": "Цвет",
            "type": "select",
            "required": True,
            "group": "variant",
            "values": ["Красный", "Синий"],
            "case_sensitive": False,
            "separator": ";",
            "unit": None,
            "allow_unit_in_value": True,
            "description": "",
        },
        {
            "id": "11",
            "name": "Вес",
            "type": "number",
            "required": False,
            "group": "variant",  # 'вес' — вариантное слово
            "values": None,
            "case_sensitive": False,
            "separator": ";",
            "unit": "килограмм",
            "allow_unit_in_value": True,
            "description": "",
        },
    ]


def test_build_validation_rules_enums_only_for_valued_attrs():
    from services.yandex_specs._parameters import _build_validation_rules

    attrs = [
        {
            "id": "10",
            "values": ["Красный"],
            "case_sensitive": False,
            "type": "select",
            "separator": ";",
        },
        {
            "id": "11",
            "values": ["a", "b"],
            "case_sensitive": False,
            "type": "multiselect",
            "separator": ";",
        },
        {"id": "12", "values": None, "type": "text", "separator": ";"},
    ]
    rules = _build_validation_rules(attrs)

    # базовые правила шаблона Маркета
    assert rules["price"] == {"min": 0.01}
    assert rules["units_per_item"] == {"min": 1, "type": "integer"}
    # enum по значениям; разделитель — только у multiselect
    assert rules["10"]["enum"] == ["Красный"]
    assert rules["10"]["separator"] is None
    assert rules["11"]["separator"] == ";"
    # без значений правила нет
    assert "12" not in rules


def test_refresh_requires_token():
    from services.yandex_specs import _refresh

    with pytest.raises(ValueError):
        asyncio.run(_refresh.refresh_yandex_specs(user_id=1, token="   "))


def test_refresh_orchestrator_pause_between_chunks(monkeypatch):
    from services.yandex_specs import _refresh

    leaves = [
        {"id": str(i), "name": f"Кат-{i}", "full_name": f"Родитель / Кат-{i}", "parent_id": "100"}
        for i in range(3)
    ]

    async def fake_tree(client, sem, headers):
        return [dict(leaf) for leaf in leaves]

    async def fake_params(client, sem, headers, category_id):
        return [
            {"id": "10", "name": "Цвет", "type": "select", "required": True, "values": ["Красный"]}
        ]

    flushed = []

    def fake_flush(user_id, buffer):
        flushed.append([(leaf["id"], spec["required_fields"][-1]) for leaf, spec in buffer])

    monkeypatch.setattr(_refresh, "fetch_yandex_categories_tree", fake_tree)
    monkeypatch.setattr(_refresh, "fetch_yandex_category_parameters", fake_params)
    monkeypatch.setattr(_refresh, "_flush_ym_buffer", fake_flush)
    monkeypatch.setattr(_refresh, "DB_CHUNK", 2)

    progress = []
    checks = iter([False, True])  # пауза запрошена перед вторым чанком

    done_keys = set()
    result = asyncio.run(
        _refresh.refresh_yandex_specs(
            user_id=1,
            token="ACMA:test",
            progress_cb=progress.append,
            pause_check=lambda: next(checks),
            done_keys=done_keys,
        )
    )

    # первый чанк (2 категории) сохранён и закоммичен, второй не начат
    assert result["paused"] is True
    assert result["fetched"] == 2
    assert result["errors"] == 0
    assert flushed == [[("0", "Цвет"), ("1", "Цвет")]]
    # ключи закоммиченного чанка вернулись задаче (реестр для resume)
    assert done_keys == {"0", "1"}
    # колбэк получил общий размер до старта обработки
    assert progress[0] == {"total": 3, "fetched": 0, "errors": 0}


def test_refresh_orchestrator_full_run_with_skip_and_errors(monkeypatch):
    from services.yandex_specs import _refresh

    leaves = [
        {"id": str(i), "name": f"Кат-{i}", "full_name": f"Родитель / Кат-{i}", "parent_id": "100"}
        for i in range(3)
    ]

    async def fake_tree(client, sem, headers):
        return [dict(leaf) for leaf in leaves]

    async def fake_params(client, sem, headers, category_id):
        if category_id == "1":
            raise RuntimeError("boom")
        return []

    flushed = []

    def fake_flush(user_id, buffer):
        flushed.append([(leaf["id"], spec["special_requirements"]) for leaf, spec in buffer])

    monkeypatch.setattr(_refresh, "fetch_yandex_categories_tree", fake_tree)
    monkeypatch.setattr(_refresh, "fetch_yandex_category_parameters", fake_params)
    monkeypatch.setattr(_refresh, "_flush_ym_buffer", fake_flush)

    progress = []
    done_keys = set()
    result = asyncio.run(
        _refresh.refresh_yandex_specs(
            user_id=1,
            token="ACMA:test",
            category_ids=["0", "1", "2"],
            skip_category_ids=["2"],  # уже сохранена до паузы — пропустить
            progress_cb=progress.append,
            done_keys=done_keys,
        )
    )

    # leaf "2" пропущен (skip_category_ids), leaf "1" упал
    assert result == {
        "platform": "yandex",
        "fetched": 1,
        "errors": 1,
        "error_details": [{"category_id": "1", "error": "boom"}],
    }
    # упавшая категория не попала в буфер записи
    assert [leaf_id for leaf_id, _ in flushed[0]] == ["0"]
    # спецтребования несут имя и id категории Маркета
    assert flushed[0][0][1] == {"yandex_category_name": "Кат-0", "yandex_category_id": "0"}
    assert done_keys == {"0"}
    # финальный прогресс дошёл до колбэка
    assert progress[-1] == {"total": 2, "fetched": 1, "errors": 1}


def test_refresh_orchestrator_empty_selection(monkeypatch):
    from services.yandex_specs import _refresh

    async def fake_tree(client, sem, headers):
        return [{"id": "9", "name": "Кат", "full_name": "Кат", "parent_id": None}]

    monkeypatch.setattr(_refresh, "fetch_yandex_categories_tree", fake_tree)

    result = asyncio.run(
        _refresh.refresh_yandex_specs(user_id=1, token="ACMA:test", category_ids=["777"])
    )

    assert result == {"platform": "yandex", "fetched": 0, "errors": 0, "error_details": []}
