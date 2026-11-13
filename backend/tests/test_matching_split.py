"""Р20: гарантия, что разбиение tasks/matching.py (459 строк) на пакет
сохранило публичный API и поведение.

Импортёры не менялись: tasks/catalog_tasks/_refresh —
`_spec_cache_invalidate`; tasks/migrate_tasks/_single и _batch —
`_pick_target_category`, `_ensure_canonical_attributes`, `_base_source`,
`_safe_float`; tests/test_money_helpers.py — `_base_source`, `_safe_float`,
`_stem_ru`. Точки патчинга тестов migrate_tasks — подмодули _single/_batch
(имена импортированы туда) — стабильны.

Кэш спеков (P-3) наполняется напрямую в сторы _cache (без БД): TTL-метка
делает _spec_cache_load no-op, тела функций работают на чистых данных.
"""

import time

import tasks.matching as pkg
import tasks.matching._cache as cache_mod
import tasks.matching._match as match_mod
from tasks.matching._attrs import (
    CANON_ATTRS as attrs_CANON_ATTRS,
)
from tasks.matching._attrs import (
    TNVED_NAMES as attrs_TNVED_NAMES,
)
from tasks.matching._attrs import (
    _ensure_canonical_attributes as from_attrs,
)
from tasks.matching._cache import _spec_cache_invalidate as from_cache
from tasks.matching._match import _pick_target_category as from_match
from tasks.matching._text import (
    _base_source as text_base_source,
)
from tasks.matching._text import (
    _norm_name,
)
from tasks.matching._text import (
    _safe_float as text_safe_float,
)
from tasks.matching._text import (
    _stem_ru as text_stem_ru,
)


def test_public_api_preserved():
    # публичные имена пакета — те же объекты, что в подмодулях
    assert pkg._base_source is text_base_source
    assert pkg._safe_float is text_safe_float
    assert pkg._stem_ru is text_stem_ru
    assert pkg._spec_cache_invalidate is from_cache
    assert pkg._pick_target_category is from_match
    assert pkg._ensure_canonical_attributes is from_attrs
    assert pkg.CANON_ATTRS is attrs_CANON_ATTRS
    assert pkg.TNVED_NAMES is attrs_TNVED_NAMES
    # полный каталог поверхности пакета
    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {"CANON_ATTRS", "TNVED_NAMES"}


def test_importers_same_objects():
    # `from tasks.matching import X` — как в migrate_tasks/_single, _batch и test_money_helpers
    from tasks.matching import (
        _base_source,
        _ensure_canonical_attributes,
        _pick_target_category,
        _safe_float,
        _spec_cache_invalidate,
        _stem_ru,
    )

    assert _base_source is pkg._base_source
    assert _safe_float is pkg._safe_float
    assert _stem_ru is pkg._stem_ru
    assert _spec_cache_invalidate is pkg._spec_cache_invalidate
    assert _pick_target_category is pkg._pick_target_category
    assert _ensure_canonical_attributes is pkg._ensure_canonical_attributes


def test_canon_attrs_config():
    # конфигурация канонических атрибутов Ozon — 4 домена + 3 имени ТН ВЭД
    assert set(pkg.CANON_ATTRS) == {"brand", "model", "type", "marking"}
    assert pkg.CANON_ATTRS["brand"]["fallback"] == "NoName"
    assert pkg.CANON_ATTRS["type"]["fallback"] == "Футболка"
    assert pkg.CANON_ATTRS["marking"]["fallback"] == "Нет"
    assert pkg.CANON_ATTRS["model"]["fallback"] is None
    assert attrs_TNVED_NAMES == ["тнвэдкодыеаэс", "тнвэд", "кодытнвэд"]
    assert _norm_name("ТН ВЭД коды ЕАЭС") == "тнвэдкодыеаэс"


def _fresh_stores():
    """Полный сброс P-3 кэша (оригинальные объекты — их же видит _match.py,
    импортировавший ссылки from .. import) и наполнение тестовыми данными."""
    pkg._spec_cache_invalidate()


def _fill_cache(platform, names):
    """Наполняет сторы P-3 кэша (оригинальные словари) и ставит свежую TTL-метку."""
    cache_mod._spec_cache_names[platform] = list(names)
    cache_mod._spec_cache_names_set[platform] = {str(n).strip() for n in names}
    cache_mod._spec_cache_specs[platform] = {}
    cache_mod._spec_cache_has[platform] = bool(names)
    cache_mod._spec_cache_ts[platform] = time.monotonic()


def test_spec_cache_invalidate_platform_vs_all():
    _fresh_stores()

    _fill_cache("ozon", ["А / Футболки"])
    _fill_cache("wildberries", ["Платья"])

    # сброс одной площадки: остальные живут
    pkg._spec_cache_invalidate("ozon")
    assert "ozon" not in cache_mod._spec_cache_names
    assert "ozon" not in cache_mod._spec_cache_ts
    assert cache_mod._spec_cache_names["wildberries"] == ["Платья"]

    # полный сброс
    pkg._spec_cache_invalidate()
    assert not cache_mod._spec_cache_names
    assert not cache_mod._spec_cache_names_set
    assert not cache_mod._spec_cache_specs
    assert not cache_mod._spec_cache_has
    assert not cache_mod._spec_cache_ts


def test_spec_name_exists_and_platform_has_any_specs():
    _fresh_stores()

    # TTL-метка свежая: _spec_cache_load выходит по метрике, не открывая сессию БД
    _fill_cache("ozon", ["Одежда / Футболки", "Дом и сад"])
    _fill_cache("пустая", [])  # есть метка, но справочник пуст
    from tasks.matching._cache import _platform_has_any_specs, _spec_name_exists

    assert _spec_name_exists("ozon", "  Одежда / Футболки ")
    assert not _spec_name_exists("ozon", "Несуществующая")
    assert not _spec_name_exists("ozon", "")
    assert _platform_has_any_specs("ozon")
    assert not _platform_has_any_specs("пустая")
    _fresh_stores()


def test_match_spec_by_text_scoring():
    _fresh_stores()

    # свежая TTL-метка: _spec_cache_load — no-op, БД не открывается
    cache_mod._spec_cache_names["ozon"] = [
        "Одежда / Футболки",            # точное вхождение типа в текст → score 120+
        "Одежда / Футболки с принтом",  # стемминг общий → score 100+
        "Дом и сад / Пледы",
    ]
    cache_mod._spec_cache_ts["ozon"] = time.monotonic()
    from tasks.matching._match import _match_spec_by_text

    # точное вхождение «футболки» бьёт стемминг-совпадения
    assert _match_spec_by_text("Детские футболки", "ozon") == "Одежда / Футболки"
    # множественное число сводится стеммингом: «футболка» <-> «Футболки»
    assert _match_spec_by_text("футболка", "ozon") is not None
    # пустые запросы
    assert _match_spec_by_text(None, "ozon") is None
    assert _match_spec_by_text("   ", "ozon") is None
    _fresh_stores()


class _FakeMapper:
    """Стаб category_mapper: авто-маппинг отключён (как пустой справочник)."""

    def auto_map_by_text(self, text, platform):
        return None

    def auto_map_to_spec(self, text, platform):
        return None


class _FakeCategoryService:
    def get_mapping_for_product(self, source, category, target, user_id):
        return None


def _stub_matching_deps(monkeypatch, *, exists=False, has_specs=True, has_tpl=False):
    """Подменяет зависимости _pick_target_category в его подмодуле."""
    monkeypatch.setattr(match_mod, "_spec_name_exists", lambda p, n: exists)
    monkeypatch.setattr(match_mod, "_platform_has_any_specs", lambda p: has_specs)
    monkeypatch.setattr(match_mod, "_match_spec_by_text", lambda t, p: None)
    monkeypatch.setattr(match_mod, "category_mapper", _FakeMapper())
    monkeypatch.setattr(match_mod, "category_service", _FakeCategoryService())
    monkeypatch.setattr(match_mod, "has_official_template", lambda *a, **k: has_tpl)
    monkeypatch.setattr(match_mod, "detect_platform", lambda s: "ozon")


def test_pick_target_category_modal_wins(monkeypatch):
    _stub_matching_deps(monkeypatch, exists=True)
    product = {"source": "Ozon", "category": "Старое", "name": "Платье"}

    name, src = pkg._pick_target_category(product, "Из модалки", "ozon", 1)
    assert (name, src) == ("Из модалки", "модалка")


def test_pick_target_category_no_specs_in_db_falls_back(monkeypatch):
    # спеков в БД нет → ветка 6: фолбэк-категория вместо None
    _stub_matching_deps(monkeypatch, exists=False, has_specs=False)
    product = {"source": "Ozon", "category": "Не указана", "name": "Красивое платье"}

    name, src = pkg._pick_target_category(product, None, "ozon", 1)
    assert src == "эталонный шаблон / авто-категория"
    # фолбэк-цепочка ветки 6 не включает имя товара: авто-маппинг отключён → дом по умолчанию
    assert name == "Товары для дома"


def test_pick_target_category_ozon_with_specs_not_found(monkeypatch):
    # Ozon со загруженными спеками и пустым текстом → не найдено
    _stub_matching_deps(monkeypatch, exists=False, has_specs=True, has_tpl=False)
    product = {"source": "Ozon", "category": "Не указана", "name": "Дом и сад"}

    name, src = pkg._pick_target_category(product, None, "ozon", 1)
    assert name is None
    assert src == "не найдено"


def test_ensure_canonical_attributes_non_ozon_noop(monkeypatch):
    # не Ozon — не должно быть ни спека, ни сессии БД
    def _boom(*a, **k):
        raise AssertionError("load_spec не должен вызываться для не-ozon")

    monkeypatch.setattr("tasks.matching._attrs._load_spec_for_category", _boom)
    pkg._ensure_canonical_attributes(1, "wildberries", "Что угодно", "Имя")


def test_ensure_canonical_attributes_writes_required(monkeypatch):
    import tasks.matching._attrs as attrs_mod

    spec = {
        "attributes": [
            {"name": "Бренд", "values": ["NoName", "Adidas"]},
            {"name": "Название модели", "values": []},
            {"name": "Тип", "values": ["Футболка"]},
            {"name": "Нужен код маркировки", "values": ["Нет", "Да"]},
            {"name": "ТН ВЭД коды ЕАЭС", "values": []},
        ]
    }
    added = []

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *a, **k):
            return self

        def all(self):
            return list(self._rows)

    class _FakeDB:
        def query(self, model):
            return _FakeQuery([])  # у товара ещё нет атрибутов

        def add(self, obj):
            added.append(obj)

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(attrs_mod, "_load_spec_for_category", lambda p, c: spec)
    monkeypatch.setattr(
        "tasks.matching._attrs.defaults_service.get_merged_defaults",
        lambda user_id, cat: {"brand": "Adidas", "marking": "Нет", "okpd_code": "6109"},
    )
    monkeypatch.setattr(
        "tasks.matching._attrs.defaults_service.derive_type_value",
        lambda cat, sp: "Футболка",
    )
    monkeypatch.setattr(
        "database.session.SessionLocal",
        lambda: _FakeDB(),
    )

    pkg._ensure_canonical_attributes(
        product_id=42,
        target_platform="ozon",
        target_category_name="Одежда / Футболки",
        product_name="Моя модель",
        okpd_code="6109",
        user_id=7,
    )

    names = sorted(a.name for a in added)
    values = {a.name: a.value for a in added}
    assert names == [
        "Бренд",
        "Название модели",
        "Нужен код маркировки",
        "ТН ВЭД коды ЕАЭС",
        "Тип",
    ]
    assert values["Бренд"] == "Adidas"           # дефолт-приоритет: pref из defaults
    assert values["Название модели"] == "Моя модель"  # имя товара
    assert values["Тип"] == "Футболка"            # derived_type
    assert values["Нужен код маркировки"] == "Нет"
    assert values["ТН ВЭД коды ЕАЭС"] == "6109"   # okpd_code
    assert all(a.product_id == 42 for a in added)
