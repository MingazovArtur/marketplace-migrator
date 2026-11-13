"""Р8: гарантия, что разбиение services/ozon_specs.py (635 строк) на пакет
сохранило публичный API и поведение.

Импортёр один — tasks/catalog_tasks.py: `from services.ozon_specs import
refresh_ozon_specs`. Поведение проверяем без сети: HTTP-слой (_post) и
зависимости оркестратора подменяем monkeypatch'ем в тех модулях, где они
используются (прецедент — test_category_service_split.py).
"""

import asyncio

import pytest


def test_public_api_preserved():
    import services.ozon_specs as pkg
    from services.ozon_specs import _attributes, _http, _refresh, _storage, _tree

    assert pkg.refresh_ozon_specs is _refresh.refresh_ozon_specs
    assert pkg.fetch_ozon_category_tree is _tree.fetch_ozon_category_tree
    # константы — те же объекты, что в подмодулях
    assert pkg.OZON_API_BASE is _http.OZON_API_BASE
    assert pkg.CONCURRENCY is _http.CONCURRENCY
    assert pkg.TIMEOUT is _http.TIMEOUT
    assert pkg.MAX_RETRIES is _http.MAX_RETRIES
    assert pkg.MAX_VALUES_PER_ATTR is _attributes.MAX_VALUES_PER_ATTR
    assert pkg.MAX_DICT_PAGES is _attributes.MAX_DICT_PAGES
    assert pkg.BASE_REQUIRED_FIELDS is _attributes.BASE_REQUIRED_FIELDS
    assert pkg.DB_CHUNK is _storage.DB_CHUNK
    assert pkg.PROGRESS_EVERY is _refresh.PROGRESS_EVERY

    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {
        "BASE_REQUIRED_FIELDS",
        "CONCURRENCY",
        "DB_CHUNK",
        "MAX_DICT_PAGES",
        "MAX_RETRIES",
        "MAX_VALUES_PER_ATTR",
        "OZON_API_BASE",
        "PROGRESS_EVERY",
        "TIMEOUT",
        "fetch_ozon_category_tree",
        "refresh_ozon_specs",
    }


def test_parse_ozon_key_valid():
    from services.ozon_specs._http import _parse_ozon_key

    assert _parse_ozon_key("123456:uuid-key") == ("123456", "uuid-key")
    # пробелы вокруг частей не мешают
    assert _parse_ozon_key(" 123 : secret ") == ("123", "secret")


@pytest.mark.parametrize(
    "bad",
    ["", "no-colon", "abc:key", "123:", ":key"],
)
def test_parse_ozon_key_invalid(bad):
    from services.ozon_specs._http import _parse_ozon_key

    with pytest.raises(ValueError):
        _parse_ozon_key(bad)


def test_fetch_tree_collects_enabled_leaves(monkeypatch):
    from services.ozon_specs import _tree

    payload = {
        "result": [
            # ветка с детьми — родитель для листьев
            {
                "description_category_id": 100,
                "category_name": "Электроника",
                "children": [
                    {"type_id": 7, "type_name": "Смартфоны"},
                    {"type_id": 9, "type_name": "Скрытый", "disabled": True},
                    {"type_id": 0, "type_name": "Без типа"},  # нет type_id → skip
                ],
            },
            # лист верхнего уровня без родителя → skip
            {"type_id": 5, "type_name": "Лист без родителя"},
        ]
    }

    async def fake_post(client, sem, path, body, headers):
        assert path == "/v1/description-category/tree"
        assert body == {"language": "DEFAULT"}
        return payload

    monkeypatch.setattr(_tree, "_post", fake_post)

    leaves = asyncio.run(_tree.fetch_ozon_category_tree(None, None, "123", "secret"))

    # disabled-лист отброшен, лист без type_id и без родителя пропущены
    assert leaves == [
        {
            "id": "100",
            "type_id": 7,
            "name": "Электроника",
            "type_name": "Смартфоны",
            "parent_id": None,
            "disabled": False,
        }
    ]


def test_map_attribute_types():
    from services.ozon_specs._attributes import _map_attribute

    # число
    a = _map_attribute({"id": 1, "name": "Вес", "type": "Integer", "is_required": True}, None)
    assert a == {
        "id": "1",
        "name": "Вес",
        "type": "number",
        "required": True,
        "group": "common",
        "values": None,
        "case_sensitive": True,
        "separator": ";",
        "unit": None,
        "allow_unit_in_value": True,
        "dictionary_id": 0,
    }

    # словарь → select
    a = _map_attribute(
        {"id": 2, "name": "Цвет", "type": "String", "dictionary_id": 55}, ["Красный"]
    )
    assert a["type"] == "select"
    assert a["values"] == ["Красный"]
    assert a["allow_unit_in_value"] is False

    # словарь + коллекция → multiselect с разделителем "; "
    a = _map_attribute(
        {"id": 3, "name": "Состав", "type": "String", "dictionary_id": 7, "is_collection": True},
        None,
    )
    assert a["type"] == "multiselect"
    assert a["separator"] == "; "

    # группа атрибута
    a = _map_attribute({"id": 4, "name": "Бренд", "type": "String", "group_id": 2}, None)
    assert a["group"] == "brand"

    # Boolean → select даже без словаря
    a = _map_attribute({"id": 5, "name": "Флаг", "type": "Boolean"}, None)
    assert a["type"] == "select"


def test_build_validation_rules_enums():
    from services.ozon_specs._attributes import _build_validation_rules

    attrs = [
        {
            "id": "10",
            "values": ["Красный", "Синий"],
            "case_sensitive": True,
            "type": "select",
            "separator": None,
        },
        {
            "id": "11",
            "values": ["a", "b"],
            "case_sensitive": False,
            "type": "multiselect",
            "separator": "; ",
        },
        {"id": "12", "values": None, "type": "text", "separator": None},
    ]
    rules = _build_validation_rules(attrs)

    # базовые правила на месте
    assert rules["barcode"] == {"pattern": "^[0-9]{8,14}$", "separator": ";"}
    assert rules["vat_rate"] == {"enum": ["none", "10", "22"]}
    assert rules["price"] == {"min": 0.01}
    # атрибут со значениями → enum-правило
    assert rules["10"]["enum"] == ["Красный", "Синий"]
    assert rules["10"]["case_sensitive"] is True
    # multiselect сохраняет разделитель, select — нет
    assert rules["11"]["separator"] == "; "
    assert rules["10"]["separator"] is None
    # без значений правила нет
    assert "12" not in rules


def test_build_spec_assembles_attributes_and_dictionaries(monkeypatch):
    from services.ozon_specs import _attributes

    async def fake_post(client, sem, path, body, headers):
        if path == "/v1/description-category/attribute":
            assert body["description_category_id"] == 100
            assert body["type_id"] == 7
            return {
                "result": [
                    {
                        "id": 10,
                        "name": "Цвет",
                        "type": "String",
                        "is_required": True,
                        "dictionary_id": 55,
                    },
                    {"id": 11, "name": "Вес, г", "type": "Integer", "is_required": False},
                ]
            }
        assert path == "/v1/description-category/attribute/values"
        assert body["attribute_id"] == 10
        assert body["description_category_id"] == 100
        return {"result": [{"id": 1, "value": "Красный"}, {"id": 2, "value": "Синий"}]}

    monkeypatch.setattr(_attributes, "_post", fake_post)

    leaf = {"id": "100", "type_id": 7, "name": "Электроника", "type_name": "Смартфоны"}
    spec = asyncio.run(_attributes._build_spec(None, None, {}, leaf))

    # словарь подтянулся отдельным запросом
    assert spec["attributes"][0]["values"] == ["Красный", "Синий"]
    assert spec["attributes"][0]["type"] == "select"
    assert spec["attributes"][1]["type"] == "number"
    assert spec["attributes"][1]["values"] is None

    # обязательные поля = базовые + обязательные атрибуты
    assert spec["required_fields"][:4] == [
        "Артикул",
        "Предельная цена без акций",
        "НДС, %",
        "Ссылка на главное фото",
    ]
    assert "Цвет" in spec["required_fields"]
    assert "Вес, г" not in spec["required_fields"]

    # enum-правило по словарю + спецтребования
    assert spec["validation_rules"]["10"]["enum"] == ["Красный", "Синий"]
    assert "okpd_required_for_tags" in spec["special_requirements"]
    assert spec["sheets"] == [
        "Шаблон Поставщика",
        "Документация PDF",
        "Озон.Видео",
        "Озон.Видеообложка",
    ]


def test_refresh_orchestrator_pause_between_chunks(monkeypatch):
    from services.ozon_specs import _refresh

    leaves = [
        {"id": str(i), "type_id": 7, "name": f"Кат-{i}", "type_name": "Тип"} for i in range(3)
    ]

    async def fake_tree(client, sem, client_id, api_key):
        return [dict(leaf) for leaf in leaves]

    async def fake_build_spec(client, sem, headers, leaf):
        return {
            "attributes": [],
            "required_fields": [],
            "validation_rules": {},
            "special_requirements": {},
        }

    flushed = []

    def fake_flush(user_id, buffer):
        flushed.append([(leaf["id"], leaf["type_id"]) for leaf, _ in buffer])

    monkeypatch.setattr(_refresh, "fetch_ozon_category_tree", fake_tree)
    monkeypatch.setattr(_refresh, "_build_spec", fake_build_spec)
    monkeypatch.setattr(_refresh, "_flush_buffer", fake_flush)
    monkeypatch.setattr(_refresh, "DB_CHUNK", 2)

    progress = []
    checks = iter([False, True])  # пауза запрошена перед вторым чанком

    done_keys = set()
    result = asyncio.run(
        _refresh.refresh_ozon_specs(
            user_id=1,
            raw_api_key="123:secret",
            progress_cb=progress.append,
            pause_check=lambda: next(checks),
            done_keys=done_keys,
        )
    )

    # первый чанк (2 категории) сохранён и закоммичен, второй не начат
    assert result["paused"] is True
    assert result["fetched"] == 2
    assert result["errors"] == 0
    assert flushed == [[("0", 7), ("1", 7)]]
    # ключи закоммиченного чанка вернулись задаче (реестр для resume)
    assert done_keys == {"0_7", "1_7"}
    # колбэк получил общий размер до старта обработки
    assert progress[0] == {"total": 3, "fetched": 0, "errors": 0}


def test_refresh_orchestrator_full_run_with_skip_and_errors(monkeypatch):
    from services.ozon_specs import _refresh

    leaves = [
        {"id": str(i), "type_id": 7, "name": f"Кат-{i}", "type_name": "Тип"} for i in range(3)
    ]

    async def fake_tree(client, sem, client_id, api_key):
        return [dict(leaf) for leaf in leaves]

    async def fake_build_spec(client, sem, headers, leaf):
        if leaf["id"] == "1":
            raise RuntimeError("boom")
        return {
            "attributes": [],
            "required_fields": [],
            "validation_rules": {},
            "special_requirements": {},
        }

    flushed = []

    def fake_flush(user_id, buffer):
        flushed.append([(leaf["id"], leaf["type_id"]) for leaf, _ in buffer])

    monkeypatch.setattr(_refresh, "fetch_ozon_category_tree", fake_tree)
    monkeypatch.setattr(_refresh, "_build_spec", fake_build_spec)
    monkeypatch.setattr(_refresh, "_flush_buffer", fake_flush)

    progress = []
    done_keys = set()
    result = asyncio.run(
        _refresh.refresh_ozon_specs(
            user_id=1,
            raw_api_key="123:secret",
            category_ids=["0", "1", "2"],
            skip_category_ids=["2_7"],  # уже сохранена до паузы — пропустить
            progress_cb=progress.append,
            done_keys=done_keys,
        )
    )

    # leaf "2" пропущен (skip_category_ids), leaf "1" упал
    assert result == {
        "platform": "ozon",
        "fetched": 1,
        "errors": 1,
        "error_details": [{"category_id": "1", "type_id": 7, "error": "boom"}],
    }
    # упавшая категория не попала в буфер записи
    assert flushed == [[("0", 7)]]
    assert done_keys == {"0_7"}
    # финальный прогресс дошёл до колбэка
    assert progress[-1] == {"total": 2, "fetched": 1, "errors": 1}


def test_refresh_orchestrator_empty_selection(monkeypatch):
    from services.ozon_specs import _refresh

    async def fake_tree(client, sem, client_id, api_key):
        return [{"id": "9", "type_id": 7, "name": "Кат", "type_name": "Тип"}]

    monkeypatch.setattr(_refresh, "fetch_ozon_category_tree", fake_tree)

    result = asyncio.run(
        _refresh.refresh_ozon_specs(user_id=1, raw_api_key="123:secret", category_ids=["777"])
    )

    assert result == {"platform": "ozon", "fetched": 0, "errors": 0, "error_details": []}
