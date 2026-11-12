"""Р12: гарантия, что разбиение services/spec_validator.py (618 строк) на пакет
сохранило публичный API и семантику валидации по спекам.

Импортёр (routers/export/preview.py) использует
`from services.spec_validator import validate_products_by_specs` — имя
остаётся на пакете тем же объектом, что в подмодуле.

Семантические тесты (без слова `package` в имени) используют только
публичную поверхность и прогонялись на монолите ДО разбиения — так
зафиксирована эквивалентность переноса. Тесты со словом `package`
проверяют структуру пакета (работают только на пакете).
"""

from services.spec_validator import (
    CANON_LABELS,
    OZON_TEMPLATE_REQUIRED_ORDER,
    validate_product_by_spec,
    validate_products_by_specs,
)


def _valid_product(**over):
    """Товар, полностью валидный по XLS-шаблону Ozon (без issues вовсе)."""
    product = {
        "id": 1,
        "sku": "SKU-1",
        "external_id": "EXT-1",
        "name": "Футболка с принтом",
        "price": 1000.0,
        "strike_price": 1500.0,
        "vat_rate": "none",
        "okpd_code": "6109100000",
        "barcode": "4600000000000",
        "package_weight_grams": 200,
        "package_width_mm": 300,
        "package_height_mm": 30,
        "package_length_mm": 400,
        "photos": ["https://example.com/photo.jpg"],
        "category": "Одежда",
        "attributes": [
            {"name": "Бренд", "value": "Ozon Fresh"},
            {"name": "Название модели (для объединения в одну карточку)", "value": "Модель X"},
            {"name": "Тип", "value": "Футболка"},
            {"name": "Нужен код маркировки", "value": "Нет"},
        ],
    }
    product.update(over)
    return product


_FULL_SPEC = {
    "attributes": [
        {"name": "Бренд", "type": "select", "required": True, "values": ["Ozon Fresh", "Другое"]},
        {"name": "Название модели (для объединения в одну карточку)", "type": "text"},
        {"name": "Тип", "type": "select", "required": True, "values": ["Футболка", "Лонгслив"]},
        {"name": "Нужен код маркировки", "type": "select", "values": ["Нет", "Да"]},
    ]
}


def test_full_valid_product_no_issues():
    assert validate_product_by_spec(_valid_product(), _FULL_SPEC) == []


def test_missing_base_fields_and_no_spec():
    """Пустой товар без спеки: все обязательные базовые поля — error,
    артикул/штрихкод/отсутствие спеки — warning."""
    issues = validate_product_by_spec({}, None)
    by_field = {(i["field"], i["severity"]) for i in issues}
    # обязательные колонки шаблона Ozon блокируют экспорт
    assert ("price", "error") in by_field
    assert ("vat_rate", "error") in by_field
    assert ("okpd_code", "error") in by_field
    assert ("dimensions", "error") in by_field
    assert ("main_photo", "error") in by_field
    # необязательные в файле — предупреждения
    assert ("article", "warning") in by_field
    assert ("barcode", "warning") in by_field
    assert ("spec", "warning") in by_field


def test_missing_canon_attribute_is_error():
    product = _valid_product(
        attributes=[
            {"name": "Бренд", "value": "Ozon Fresh"},
            {"name": "Тип", "value": "Футболка"},
            {"name": "Нужен код маркировки", "value": "Нет"},
        ]
    )
    issues = validate_product_by_spec(product, {"attributes": []})
    errors = [i for i in issues if i["severity"] == "error"]
    assert [i["field"] for i in errors] == ["attr:model"]
    assert CANON_LABELS["model"] in errors[0]["message"]


def test_canon_synonym_and_aggressive_normalization():
    """Синоним «Объединить на одной карточке» заполняет канон model;
    «слитное» имя спека матчится к «пробельному» значению товара через
    _norm_name (буквы+цифры в нижнем регистре)."""
    product = _valid_product(
        attributes=[
            {"name": "Бренд", "value": "Ozon Fresh"},
            {"name": "Объединить на одной карточке", "value": "Модель X"},
            {"name": "Тип", "value": "Футболка"},
            {"name": "Нужен код маркировки", "value": "Нет"},
        ]
    )
    # имя атрибута спека — слитная нормализованная форма
    spec = {"attributes": [{"name": "Названиемоделидляобъединенияводнукарточку", "type": "text"}]}
    issues = validate_product_by_spec(product, spec)
    assert [i for i in issues if i["severity"] == "error"] == []


def test_dictionary_select_values():
    # значение не из словаря у канонического select — error
    issues = validate_product_by_spec(
        _valid_product(attributes=[
            {"name": "Бренд", "value": "Ozon Fresh"},
            {"name": "Название модели (для объединения в одну карточку)", "value": "Модель X"},
            {"name": "Тип", "value": "Толстовка"},
            {"name": "Нужен код маркировки", "value": "Нет"},
        ]),
        _FULL_SPEC,
    )
    assert ("attr:Тип", "error") in {(i["field"], i["severity"]) for i in issues}

    # регистр отличается от словаря — warning (генератор исправит сам)
    issues = validate_product_by_spec(
        _valid_product(attributes=[
            {"name": "Бренд", "value": "Ozon Fresh"},
            {"name": "Название модели (для объединения в одну карточку)", "value": "Модель X"},
            {"name": "Тип", "value": "футболка"},
            {"name": "Нужен код маркировки", "value": "Нет"},
        ]),
        _FULL_SPEC,
    )
    assert ("attr:Тип", "warning") in {(i["field"], i["severity"]) for i in issues}

    # не-канонический select: значение вне словаря — только warning
    spec = {"attributes": [{"name": "Материал", "type": "select", "values": ["Хлопок"]}]}
    product = _valid_product(
        attributes=[
            {"name": "Бренд", "value": "Ozon Fresh"},
            {"name": "Название модели (для объединения в одну карточку)", "value": "Модель X"},
            {"name": "Тип", "value": "Футболка"},
            {"name": "Нужен код маркировки", "value": "Нет"},
            {"name": "Материал", "value": "Полиэстер"},
        ]
    )
    issues = validate_product_by_spec(product, spec)
    by_field = {(i["field"], i["severity"]) for i in issues}
    assert ("attr:Материал", "warning") in by_field
    assert not [i for i in issues if i["severity"] == "error"]


def test_multiselect_separator_and_limit():
    spec = {"attributes": [
        {"name": "Цвет", "type": "multiselect", "values": ["белый", "чёрный"], "max_count": 1},
    ]}
    product = _valid_product(
        attributes=[
            {"name": "Бренд", "value": "Ozon Fresh"},
            {"name": "Название модели (для объединения в одну карточку)", "value": "Модель X"},
            {"name": "Тип", "value": "Футболка"},
            {"name": "Нужен код маркировки", "value": "Нет"},
            {"name": "Цвет", "value": "белый; чёрный"},
        ]
    )
    issues = validate_product_by_spec(product, spec)
    colors = [i for i in issues if i["field"] == "attr:Цвет"]
    # разделитель «; » — авто-фикс при генерации; превышен лимит 1 из 2;
    # Цвет — не канон → оба warning
    assert [i["severity"] for i in colors] == ["warning", "warning"]
    assert not [i for i in issues if i["severity"] == "error"]


def test_number_units_and_decimal_comma():
    spec = {"attributes": [{"name": "Вес, г", "type": "number"}]}

    def _with_value(v):
        return _valid_product(
            attributes=[
                {"name": "Бренд", "value": "Ozon Fresh"},
                {"name": "Название модели (для объединения в одну карточку)", "value": "Модель X"},
                {"name": "Тип", "value": "Футболка"},
                {"name": "Нужен код маркировки", "value": "Нет"},
                {"name": "Вес, г", "value": v},
            ]
        )

    issues = validate_product_by_spec(_with_value("100 г"), spec)
    assert ("attr:Вес, г", "warning") in {(i["field"], i["severity"]) for i in issues}

    issues = validate_product_by_spec(_with_value("1,5"), spec)
    assert ("attr:Вес, г", "warning") in {(i["field"], i["severity"]) for i in issues}


def test_json_attribute_invalid_is_error():
    spec = {"attributes": [{"name": "Rich-контент JSON", "type": "text"}]}
    product = _valid_product(
        attributes=[
            {"name": "Бренд", "value": "Ozon Fresh"},
            {"name": "Название модели (для объединения в одну карточку)", "value": "Модель X"},
            {"name": "Тип", "value": "Футболка"},
            {"name": "Нужен код маркировки", "value": "Нет"},
            {"name": "Rich-контент JSON", "value": "{не json"},
        ]
    )
    issues = validate_product_by_spec(product, spec)
    errors = [i for i in issues if i["severity"] == "error"]
    assert [i["field"] for i in errors] == ["attr:Rich-контент JSON"]
    assert "невалидный JSON" in errors[0]["message"]


def test_hashtags_format_and_limit():
    spec = {"attributes": [{"name": "#хештеги", "type": "text"}]}
    tags = " ".join(["#тэг"] * 30 + ["#плох!"])
    product = _valid_product(
        attributes=[
            {"name": "Бренд", "value": "Ozon Fresh"},
            {"name": "Название модели (для объединения в одну карточку)", "value": "Модель X"},
            {"name": "Тип", "value": "Футболка"},
            {"name": "Нужен код маркировки", "value": "Нет"},
            {"name": "#хештеги", "value": tags},
        ]
    )
    issues = validate_product_by_spec(product, spec)
    msgs = [i["message"] for i in issues if i["field"] == "attr:#хештеги"]
    assert any("нарушением формата" in m and "#плох!" in m for m in msgs)
    assert any("Слишком много хештегов: 31" in m for m in msgs)


def test_excisable_category_warning():
    issues = validate_product_by_spec(
        _valid_product(category="Авто > Моторные масла"), _FULL_SPEC
    )
    assert ("excisable", "warning") in {(i["field"], i["severity"]) for i in issues}


def test_platform_gate_ozon_base_only_for_ozon():
    """Базовые поля XLS-шаблона проверяются только для platform='ozon'."""
    issues = validate_product_by_spec({}, None, platform="wildberries")
    # без ozon-базы остаётся только предупреждение об отсутствии спеки
    assert [(i["field"], i["severity"]) for i in issues] == [("spec", "warning")]


def test_batch_stats_and_duplicate_articles():
    p1 = _valid_product(sku="DUP", id=1)
    p2 = _valid_product(sku="DUP", id=2)
    p3 = _valid_product(sku="BAD", id=3, price=None)  # error: цена ≤ 0

    result = validate_products_by_specs([p1, p2, p3], {"Одежда": _FULL_SPEC})

    assert result["total"] == 3
    assert result["duplicate_articles"] == ["DUP"]
    assert result["errors"] == 1
    assert result["warnings"] == 2  # дубли артикула у p1 и p2
    assert result["products_with_errors"] == 1
    assert result["products_with_warnings"] == 2
    assert result["ready"] == 2
    assert result["ready_with_warnings"] == 2
    # перечисляются только товары с issues: все три (у p1/p2 — дубль)
    assert [item["product_id"] for item in result["issues"]] == [1, 2, 3]
    assert result["template_required"] == OZON_TEMPLATE_REQUIRED_ORDER


def test_template_required_order_constant():
    assert len(OZON_TEMPLATE_REQUIRED_ORDER) == 13
    assert OZON_TEMPLATE_REQUIRED_ORDER[0] == "Артикул"
    assert OZON_TEMPLATE_REQUIRED_ORDER[-1] == "Нужен код маркировки"
    assert "ТН ВЭД коды ЕАЭС" in OZON_TEMPLATE_REQUIRED_ORDER
    # не-Ozon площадки: чек-лист шаблона не отдаётся
    result = validate_products_by_specs([], {}, platform="wildberries")
    assert result["template_required"] == []


def test_package_public_api_preserved():
    """Все публичные имена монолита остались на пакете — те же объекты,
    что в подмодулях (импортёр routers/export/preview.py не менялся)."""
    import services.spec_validator as sv
    from services.spec_validator import _attributes, _canon, _entry, _ozon_base

    # точки входа и константы — те же объекты, что в подмодулях
    assert sv.validate_product_by_spec is _entry.validate_product_by_spec
    assert sv.validate_products_by_specs is _entry.validate_products_by_specs
    assert sv.EXCISABLE_CATEGORIES is _entry.EXCISABLE_CATEGORIES
    assert sv.CANON_LABELS is _canon.CANON_LABELS
    assert sv.OZON_TEMPLATE_REQUIRED_ORDER is _canon.OZON_TEMPLATE_REQUIRED_ORDER
    assert sv.TEMPLATE_REQUIRED_ATTRS_RAW is _canon.TEMPLATE_REQUIRED_ATTRS_RAW
    assert sv.OKPD_RE is _ozon_base.OKPD_RE
    assert sv.VALID_PHOTO_DOMAINS is _ozon_base.VALID_PHOTO_DOMAINS
    assert sv.VALID_PHOTO_EXT is _ozon_base.VALID_PHOTO_EXT
    assert sv.HASHTAG_RE is _attributes.HASHTAG_RE

    # подмодули связаны через те же объекты (без копий)
    assert _attributes._SYNONYM_INDEX is _canon._SYNONYM_INDEX
    assert _attributes._norm_name is _canon._norm_name
    assert _entry._validate_ozon_base is _ozon_base._validate_ozon_base
    assert _entry._validate_attributes is _attributes._validate_attributes

    # на пакете нет случайных публичных имён (полный каталог поверхности)
    public = {n for n in dir(sv) if not n.startswith("_")}
    assert public == {
        "CANON_LABELS",
        "EXCISABLE_CATEGORIES",
        "HASHTAG_RE",
        "OKPD_RE",
        "OZON_TEMPLATE_REQUIRED_ORDER",
        "TEMPLATE_REQUIRED_ATTRS_RAW",
        "VALID_PHOTO_DOMAINS",
        "VALID_PHOTO_EXT",
        "validate_product_by_spec",
        "validate_products_by_specs",
    }


def test_package_canon_normalization():
    from services.spec_validator._canon import _is_canon_attr, _norm_name

    # агрессивная нормализация: пробелы и пунктуация не важны
    assert _norm_name("Название модели (для объединения в одну карточку)") == _norm_name(
        "Названиемоделидляобъединенияводнукарточку"
    )
    # синонимы спеков сводятся к канонам
    assert _is_canon_attr("Бренд") == "brand"
    assert _is_canon_attr("Бренд в одежде и обуви") == "brand"
    assert _is_canon_attr("Объединить в одну карточку") == "model"
    assert _is_canon_attr("Маркировка") == "marking"
    # постороннее имя — не канон
    assert _is_canon_attr("Материал") is None
    assert _is_canon_attr("") is None
