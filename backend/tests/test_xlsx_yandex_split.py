"""Р23: гарантия, что разбиение services/xlsx_generator/yandex.py (362 строки)
на под-пакет не потеряло публичный API и поведение.

Импортёр один — services/xlsx_generator/__init__.py:
`from services.xlsx_generator.yandex import build_yandex_workbook`
(не менялся); используется в резервной ветке generate_export, когда
эталонный шаблон Яндекс Маркета не загружен (has_official_template False).

Мёртвый хвостовой комментарий монолита «===== Сборка книги Ozon =====»
(ниже него кода не было) удалён — на AST и поведение не влияет.
"""

import services.xlsx_generator as xlsx_pkg
import services.xlsx_generator.yandex as pkg
from services.xlsx_generator.yandex._book import build_yandex_workbook as from_book
from services.xlsx_generator.yandex._instruction import (
    _populate_yandex_instruction_sheet as from_instruction,
)
from services.xlsx_generator.yandex._values import (
    _guess_yandex_category as from_values_guess,
    _yandex_cell_value as from_values_cell,
)


def test_public_api_preserved():
    assert pkg.build_yandex_workbook is from_book
    assert pkg._guess_yandex_category is from_values_guess
    assert pkg._yandex_cell_value is from_values_cell
    assert pkg._populate_yandex_instruction_sheet is from_instruction
    # реэкспорт через xlsx_generator — как в монолите
    assert xlsx_pkg.build_yandex_workbook is from_book
    # полный каталог поверхности пакета
    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {"build_yandex_workbook"}


def test_guess_category_from_mapped_and_rules():
    # валидная mapped_category берётся последним сегментом пути
    p = {"mapped_category": "Одежда / Футболки", "name": "что угодно"}
    assert from_values_guess(p) == "Футболки"
    # невалидные значения игнорируются, срабатывают правила по имени
    p = {"mapped_category": "Не указана", "category": "Без категории", "name": "Красное платье"}
    assert from_values_guess(p) == "Платья и сарафаны"
    p = {"name": "Смартфон Galaxy A54"}
    assert from_values_guess(p) == "Мобильные телефоны"
    # незнакомое имя → дом по умолчанию
    assert from_values_guess({"name": "Кодеин一瓶"}) == "Товары для дома"


def test_cell_value_variants():
    # article: каскад _article → sku → external_id → YM-{id}
    assert from_values_cell({"id": 9}, "article", {}) == "YM-9"
    assert from_values_cell({"id": 9, "_article": "A1"}, "article", {}) == "A1"
    # brand: синонимы «без бренда» → нормализуется в «Нет бренда»
    assert from_values_cell({"brand": "NoName"}, "brand", {}) == "Нет бренда"
    assert from_values_cell({"brand": "Adidas"}, "brand", {}) == "Adidas"
    # вес: граммы → килограммы с 3 знаками
    assert from_values_cell({"package_weight_grams": 1500}, "weight_kg", {}) == 1.5
    # габариты: мм → см
    assert from_values_cell({"package_length_mm": 655}, "length_cm", {}) == 65.5
    # маркировка: только явное «да»
    assert from_values_cell({"id": 1}, "marking", {"нуженкодмаркировки": "Да"}) == "Да"
    assert from_values_cell({"id": 1}, "marking", {"нуженкодмаркировки": "Нет"}) is None
    # характеристики: системные атрибуты (skip_norms) исключаются
    p = {
        "id": 1,
        "attributes": [
            {"name": "Бренд", "value": "X"},
            {"name": "Цвет", "value": "Красный"},
        ],
    }
    assert from_values_cell(p, "ym_characteristics", {}) == "Цвет|Красный"
    # архивные всегда «Нет»
    assert from_values_cell({"id": 1}, "archived", {}) == "Нет"
    # photos: до 30, через запятую
    p = {"photos": [f"http://x/{i}.jpg" for i in range(40)]}
    assert from_values_cell(p, "photos_comma", {}).count(",") == 29
    # неизвестный ключ → None
    assert from_values_cell({"id": 1}, "no_such_key", {}) is None
    assert from_values_cell({"id": 1}, None, {}) is None


def test_build_workbook_smoke():
    products = [
        {
            "id": 1,
            "name": "Футболка с принтом",
            "price": 1990.0,
            "sku": "T-100",
            "category": "Одежда / Футболки",
            "brand": "Adidas",
            "photos": ["http://x/1.jpg"],
            "description": "Хлопок <b>100%</b>",
        }
    ]
    wb = from_book(products)
    assert wb.sheetnames == ["Инструкция", "Список товаров"]
    assert wb.active.title == "Список товаров"
    ws = wb["Список товаров"]
    assert ws.max_row >= 4  # 3 строки шапки + товар
    # высоты строк шапки фиксированы шаблоном
    assert ws.row_dimensions[1].height == 26
    assert ws.row_dimensions[2].height == 28
    assert ws.row_dimensions[3].height == 95


def test_instruction_sheet_steps():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Инструкция"
    from_instruction(ws)
    assert ws["A1"].value == "Инструкция"
    assert ws["A2"].value == "Шаг 1. Заполните шаблон"
    texts = [str(ws.cell(row=r, column=1).value or "") for r in range(1, ws.max_row + 1)]
    assert any("Шаг 2. Загрузите шаблон в систему" in t for t in texts)
    assert any("Шаг 3. Дождитесь проверки ассортимента" in t for t in texts)
    assert any("Статус карточки" == t for t in texts)
    assert "Подробнее о статусах можно узнать в Справке." in texts


def test_workbook_writes_product_data():
    from services.xlsx_generator.columns import YANDEX_TEMPLATE_COLUMNS

    products = [
        {
            "id": 5,
            "name": "Платье летнее",
            "price": 2990.0,
            "sku": "P-5",
            "category": "Одежда / Платья",
        }
    ]
    wb = from_book(products)
    ws = wb["Список товаров"]
    # колонка с key="name" и key="price" заполняется в строке 4
    for col_idx, (header, key, required, is_gray, group_title, hint) in enumerate(
        YANDEX_TEMPLATE_COLUMNS, start=1
    ):
        if is_gray:
            continue  # серые колонки не заполняются
        if key == "name":
            assert ws.cell(row=4, column=col_idx).value == "Платье летнее"
        if key == "category":
            assert ws.cell(row=4, column=col_idx).value == "Платья"
        if key == "price":
            assert ws.cell(row=4, column=col_idx).value == 2990.0


def test_unique_articles_applied_in_builder():
    # build_yandex_workbook вызывает _unique_articles: артикул из sku, дубли суффиксуются
    products = [
        {"id": 1, "name": "A", "sku": "DUP"},
        {"id": 2, "name": "B", "sku": "DUP"},
    ]
    wb = from_book(products)
    ws = wb["Список товаров"]
    from services.xlsx_generator.columns import YANDEX_TEMPLATE_COLUMNS

    values = []
    for col_idx, (_, key, _, is_gray, _, _) in enumerate(YANDEX_TEMPLATE_COLUMNS, start=1):
        if not is_gray and key == "article":
            values.append(ws.cell(row=4, column=col_idx).value)
            values.append(ws.cell(row=5, column=col_idx).value)
    assert values == ["DUP", "DUP_2"]
