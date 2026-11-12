"""Р11: гарантия, что разбиение services/tnved_mapper.py (694 строки) на пакет
сохранило публичный API, порядок ключей справочника и семантику поиска.

Импортёр (routers/tnved.py) использует `from services.tnved_mapper import
get_tnved_description, search_tnved, suggest_tnved` — все имена должны
остаться на пакете теми же объектами, что в подмодулях.

Порядок ключей TNVED_DATABASE МАТЕРИАЛЕН: search_tnved возвращает первые
10 совпадений В ПОРЯДКЕ справочника, suggest_tnved при равном score
сохраняет порядок справочника. Справочник разбит последовательными
строками на _database_a/_database_b, и склейка {**A, **B} обязана
воспроизводить монолит: позиция дублированного ключа — из A (первое
вхождение в литерале), значение — из B (последний литерал побеждал
и в монолите).
"""

import services.tnved_mapper as tnved
from services.tnved_mapper import (
    TNVED_DATABASE,
    _database,
    _database_a,
    _database_b,
    _lookup,
)


def test_public_api_preserved():
    assert tnved.suggest_tnved is _lookup.suggest_tnved
    assert tnved.get_tnved_description is _lookup.get_tnved_description
    assert tnved.search_tnved is _lookup.search_tnved
    assert tnved.TNVED_DATABASE is _database.TNVED_DATABASE
    # _lookup ходит по тому же словарю, что отдаётся с пакета
    assert _lookup.TNVED_DATABASE is TNVED_DATABASE

    # на пакете нет случайных публичных имён
    public = {n for n in dir(tnved) if not n.startswith("_")}
    assert public == {
        "TNVED_DATABASE",
        "suggest_tnved",
        "get_tnved_description",
        "search_tnved",
    }


def test_key_order_and_cross_values():
    """Склейка {**A, **B} == монолит: порядок ключей A + новые из B;
    для сквозных дублей значение из B, позиция — из A."""
    a = _database_a.TNVED_DATABASE_A
    b = _database_b.TNVED_DATABASE_B

    # 569 уникальных ключей монолита (580 литералов, 11 продублированных)
    assert len(TNVED_DATABASE) == 569

    expected_keys = list(a) + [k for k in b if k not in a]
    assert list(TNVED_DATABASE) == expected_keys

    cross = [k for k in b if k in a]
    assert cross, "сквозные дубли частей обязаны существовать (11 ключей)"
    for k in cross:
        # значение — из B (последний литерал монолита побеждал)
        assert TNVED_DATABASE[k] == b[k]
    # а позиция — из A (первое вхождение): дубли не «уезжают» в конец
    for k in cross:
        assert list(TNVED_DATABASE).index(k) == list(a).index(k)
    # количество сходится: уникальные A + уникальные B − сквозные дубли
    assert len(TNVED_DATABASE) == len(a) + len(b) - len(cross)


def test_suggest_tnved_semantics():
    from services.tnved_mapper import suggest_tnved

    # пустое имя или нет совпадений — пустой список
    assert suggest_tnved("", "Одежда") == []
    assert suggest_tnved("zzz нет такого товара qqq", "") == []

    # категория участвует в поиске наравне с названием
    res = suggest_tnved("Зимний набор", "Одежда / Носки")
    assert [m["keyword"] for m in res] == ["носки"]

    # чем длиннее совпавшее слово, тем выше релевантность
    res = suggest_tnved("пуховик и пальто", "")
    assert [(m["keyword"], m["score"]) for m in res] == [("пуховик", 7), ("пальто", 6)]

    # при равном score сохраняется порядок справочника (стабильная сортировка):
    # «пальто» стоит в справочнике раньше «куртки»
    res = suggest_tnved("куртка и пальто", "")
    assert [(m["keyword"], m["score"]) for m in res] == [("пальто", 6), ("куртка", 6)]

    # топ-3: из 4 совпадений (футболка, лонгслив, майка, носки) носки
    # отбрасываются — score 5 при равенстве с «майкой», но «майка» раньше
    # в справочнике; «футболка» (8) выше «лонгслива» (8) тоже порядком
    res = suggest_tnved("футболка майка лонгслив носки", "")
    assert [(m["keyword"], m["score"]) for m in res] == [
        ("футболка", 8),
        ("лонгслив", 8),
        ("майка", 5),
    ]

    # в ответе — keyword/code/description/score
    top = suggest_tnved("Футболка мужская хлопковая черная", "")
    assert top[0]["code"] == "6109100000"
    assert top[0]["description"] == TNVED_DATABASE["футболка"]["desc"]


def test_get_tnved_description_semantics():
    from services.tnved_mapper import get_tnved_description

    assert get_tnved_description("6109100000") == (
        "Футболки и майки трикотажные машинного или ручного вязания"
    )
    # неизвестный или пустой код — None (без исключений)
    assert get_tnved_description("0000000000") is None
    assert get_tnved_description("") is None


def test_search_tnved_semantics():
    from services.tnved_mapper import search_tnved

    # пустой запрос — пустой список
    assert search_tnved("") == []
    assert search_tnved("zzzqqq") == []

    # ищет по ключевому слову, коду и описанию — в порядке справочника
    res = search_tnved("футбол")
    assert [(r["keyword"], r["code"]) for r in res] == [
        ("футболка", "6109100000"),
        ("лонгслив", "6109100000"),  # совпадение по описанию
        ("мяч", "9506620000"),  # «Мячи надувные (футбольные, ...)»
        ("футбольный мяч", "9506620000"),
    ]

    # поиск по префиксу кода
    assert [r["keyword"] for r in search_tnved("6109")] == ["футболка", "майка", "лонгслив"]

    # максимум 10 результатов («трикотажные» встречается чаще)
    assert len(search_tnved("трикотажные")) == 10
