"""
Билдер книги AliExpress: структура 1:1 с официальным XLSX-шаблоном AliExpress Russia
(«Товары → Массовые операции Excel → Загрузить → Скачать шаблон категории»).

Структура листа «Шаблон» (по официальной документации и скриншотам):
  строка 1 — названия блоков (объединённые ячейки):
      «Основные характеристики»,
      «Произвольные характеристики продавца» (5 колонок),
      «Информация о модификации товара (SKU). Товары с разной модификацией,
       но одинаковым SPU ID объединяются в одну карточку»;
  строка 2 — подсказки над полями (допустимые значения, длины, форматы);
  строка 3 — заголовки колонок (обязательные отмечены звёздочкой *),
             здесь же — названия произвольных характеристик продавца;
  строка 4+ — данные (одна строка = одна модификация / SKU).

Вариации разворачиваются в отдельные строки: одинаковый «Модель (seller SPU ID)»,
уникальный «Артикул/Штрихкод (seller SKU ID)», уникальные Цвет/Размер.
"""

import math

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from services.template_filler import (
    _build_enum_fix,
    _expand_products_for_platform,
    _norm,
    _row_values,
)
from services.xlsx_generator.common import _add_dict_sheet, _fill_dict_sheet

# ==================== Строки шапки ====================

BLOCK_ROW = 1
HINT_ROW = 2
HEADER_ROW = 3
DATA_START_ROW = 4

CUSTOM_ATTR_COUNT = 5

# ==================== Блоки (строка 1) ====================

AE_MAIN_BLOCK = "Основные характеристики"
AE_CUSTOM_BLOCK = "Произвольные характеристики продавца"
AE_SKU_BLOCK = (
    "Информация о модификации товара (SKU). Товары с разной модификацией, "
    "но одинаковым SPU ID объединяются в одну карточку"
)

AE_CUSTOM_HINT = (
    "Добавьте произвольную характеристику: в строке ниже укажите её название, "
    "а в строках товаров — любое значение для этой характеристики."
)

# ==================== Колонки: (заголовок, обязательная, подсказка, ключ значений) ====================

AE_MAIN_COLUMNS = [
    (
        "Модель (seller SPU ID)",
        True,
        "Модель товара. Может быть равна Артикулу (SKU ID). Товары одной модели "
        "будут отображаться на одной карточке. Не более 50 символов.",
        "модельsellerspuid",
    ),
    (
        "Артикул/Штрихкод (seller SKU ID)",
        True,
        "Уникальный артикул или штрихкод товара в системе продавца. "
        "Не более 50 символов. Добавление артикула создаёт вариации.",
        "артикулштрихкодsellerskuid",
    ),
    (
        "Штрихкод / EAN",
        False,
        "Уникальный штрихкод / EAN товара. Обязателен, если отгружаете на склады Cainiao. "
        "Не более 20 цифр. После создания товара изменить нельзя.",
        "штрихкодean",
    ),
    (
        "GTIN",
        False,
        "Если указан и товар маркируемый, система автоматически найдёт коды ОКПД2 и ТН ВЭД ЕАЭС.",
        "gtin",
    ),
    (
        "Наименование товара",
        True,
        "Составьте название по правилам AliExpress: тип товара + бренд + модель + "
        "отличительные характеристики.",
        "наименованиетовара",
    ),
    (
        "Описание",
        True,
        "Можно использовать текст или HTML. Поддерживаются только определённые теги и форматирование.",
        "описание",
    ),
    (
        "Бренд",
        True,
        "Зарегистрируйте бренд заранее. Если у товара нет бренда — укажите NONE.",
        "бренд",
    ),
    (
        "Главное фото",
        True,
        "Прямая ссылка на основное изображение товара (JPG/PNG).",
        "главноефото",
    ),
    (
        "Ссылки на дополнительные фото",
        False,
        "Прямые ссылки на дополнительные изображения через пробел (до 14 шт.).",
        "ссылкинадополнительныефото",
    ),
]

AE_SKU_COLUMNS = [
    (
        "Фото SKU",
        False,
        "Ссылка на изображение вариации товара.",
        "фотоsku",
    ),
    (
        "Цвет",
        True,
        "Значение выбирайте из списка. Для вариаций заполняйте отдельной строкой для каждой.",
        "цвет",
    ),
    (
        "Размер",
        False,
        "Значение выбирайте из списка. Для вариаций заполняйте отдельной строкой для каждой.",
        "размер",
    ),
    (
        "Доставка из",
        True,
        "Страна, из которой отправляется товар.",
        "доставкаиз",
    ),
    (
        "Название цвета в системе продавца",
        False,
        "Соответствие между цветом в системе AliExpress и вашим названием. В вариациях не учитывается.",
        "названиецветавсистемепродавца",
    ),
    (
        "Название размера в системе продавца",
        False,
        "Соответствие между размером в системе AliExpress и вашим названием. В вариациях не учитывается.",
        "названиеразмеравсистемепродавца",
    ),
    (
        "Вес с упаковкой",
        True,
        "Только цифры 0,0–9999999,99 (кг), без единиц измерения. Не может быть равен нулю.",
        "вессупаковкой",
    ),
    (
        "Длина упаковки",
        True,
        "Только целые числа (см), без единиц измерения. Не может быть равна нулю.",
        "длинаупаковки",
    ),
    (
        "Ширина упаковки",
        True,
        "Только целые числа (см), без единиц измерения. Не может быть равна нулю.",
        "ширинаупаковки",
    ),
    (
        "Высота упаковки",
        True,
        "Только целые числа (см), без единиц измерения. Не может быть равна нулю.",
        "высотаупаковки",
    ),
    (
        "Цена",
        True,
        "Только цифры 0,0–9999999,99, без единиц измерения и символов валют.",
        "цена",
    ),
    (
        "Остаток",
        True,
        "Только целые значения 0–9999999.",
        "остаток",
    ),
]

# Нормализованные ключи стандартных колонок — произвольные характеристики их не дублируют
AE_STANDARD_NORMS = (
    {_norm(h) for _, _, _, h in AE_MAIN_COLUMNS + AE_SKU_COLUMNS}
    | {"бренд", "цвет", "размер", "модель", "тип"}
)

# ==================== Стили ====================

BLOCK_FILLS = {
    AE_MAIN_BLOCK: PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid"),
    AE_CUSTOM_BLOCK: PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid"),
    AE_SKU_BLOCK: PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid"),
}
BLOCK_FONT = Font(name="Arial", size=10, bold=True)
HINT_FONT = Font(name="Arial", size=8, color="666666")
HEADER_FONT = Font(name="Arial", size=10, bold=True)
HEADER_REQUIRED_FONT = Font(name="Arial", size=10, bold=True, color="C00000")
DATA_FONT = Font(name="Arial", size=10)
WRAP = Alignment(wrap_text=True, vertical="top")


# ==================== Публичные функции ====================


def aliexpress_custom_attr_names(products: list) -> list[str]:
    """
    До 5 произвольных характеристик продавца: названия атрибутов товаров,
    которых нет среди стандартных колонок шаблона.
    """
    collected: list[str] = []
    seen: set[str] = set()
    for p in products:
        for a in p.get("attributes") or []:
            name = (a.get("name") or "").strip()
            norm = _norm(name)
            if name and norm and norm not in AE_STANDARD_NORMS and norm not in seen:
                seen.add(norm)
                collected.append(name)
                if len(collected) >= CUSTOM_ATTR_COUNT:
                    return collected
    return collected


def aliexpress_flat_rows(products: list, spec: dict | None = None) -> list[dict]:
    """
    Плоские строки (заголовок → значение) для предпросмотра выгрузки.
    Вариации разворачиваются так же, как в итоговом файле.
    """
    expanded = _expand_products_for_platform(products, "aliexpress")
    enum_fix = _build_enum_fix(spec)
    custom_names = aliexpress_custom_attr_names(products)

    rows: list[dict] = []
    for i, p in enumerate(expanded, start=1):
        values = _row_values(p, i, enum_fix, platform="aliexpress")
        row: dict = {}
        for header, _req, _hint, key in AE_MAIN_COLUMNS:
            row[header] = values.get(key)
        for name in custom_names:
            row[name] = values.get(_norm(name))
        for header, _req, _hint, key in AE_SKU_COLUMNS:
            row[header] = values.get(key)
        rows.append(row)
    return rows


def build_aliexpress_workbook(products: list, spec: dict | None = None) -> Workbook:
    """Собирает книгу в структуре официального XLSX-шаблона AliExpress."""
    expanded = _expand_products_for_platform(products, "aliexpress")
    enum_fix = _build_enum_fix(spec)
    custom_names = aliexpress_custom_attr_names(products)

    rows_values = [
        _row_values(p, i, enum_fix, platform="aliexpress")
        for i, p in enumerate(expanded, start=1)
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "Шаблон"

    n_main = len(AE_MAIN_COLUMNS)
    n_custom = CUSTOM_ATTR_COUNT
    custom_start = n_main + 1
    sku_start = custom_start + n_custom
    total_cols = sku_start + len(AE_SKU_COLUMNS) - 1
    last_row = max(DATA_START_ROW + len(rows_values) - 1, DATA_START_ROW) + 50

    # --- Строка 1: блоки ---
    ws.cell(row=BLOCK_ROW, column=1, value=AE_MAIN_BLOCK)
    ws.merge_cells(
        start_row=BLOCK_ROW, start_column=1, end_row=BLOCK_ROW, end_column=n_main
    )
    ws.cell(row=BLOCK_ROW, column=custom_start, value=AE_CUSTOM_BLOCK)
    ws.merge_cells(
        start_row=BLOCK_ROW,
        start_column=custom_start,
        end_row=BLOCK_ROW,
        end_column=custom_start + n_custom - 1,
    )
    c_sku = ws.cell(row=BLOCK_ROW, column=sku_start, value=AE_SKU_BLOCK)
    ws.merge_cells(
        start_row=BLOCK_ROW,
        start_column=sku_start,
        end_row=BLOCK_ROW,
        end_column=total_cols,
    )
    for col in range(1, total_cols + 1):
        cell = ws.cell(row=BLOCK_ROW, column=col)
        block = (
            AE_MAIN_BLOCK
            if col <= n_main
            else (AE_CUSTOM_BLOCK if col < sku_start else AE_SKU_BLOCK)
        )
        cell.fill = BLOCK_FILLS[block]
        cell.font = BLOCK_FONT
        cell.alignment = WRAP

    # --- Строка 2: подсказки + строка 3: заголовки ---
    used_dicts: dict = {}
    for col, (header, required, hint, _key) in enumerate(AE_MAIN_COLUMNS, start=1):
        ws.cell(row=HINT_ROW, column=col, value=hint).font = HINT_FONT
        ws.cell(row=HINT_ROW, column=col).alignment = WRAP
        h = ws.cell(row=HEADER_ROW, column=col, value=header + ("*" if required else ""))
        h.font = HEADER_REQUIRED_FONT if required else HEADER_FONT
        h.alignment = WRAP

    for idx, name in enumerate(custom_names):
        col = custom_start + idx
        h = ws.cell(row=HEADER_ROW, column=col, value=name)
        h.font = HEADER_FONT
        h.alignment = WRAP
    for col in range(custom_start, sku_start):
        ws.cell(row=HINT_ROW, column=col, value=AE_CUSTOM_HINT).font = HINT_FONT
        ws.cell(row=HINT_ROW, column=col).alignment = WRAP

    for idx, (header, required, hint, _key) in enumerate(AE_SKU_COLUMNS, start=sku_start):
        ws.cell(row=HINT_ROW, column=idx, value=hint).font = HINT_FONT
        ws.cell(row=HINT_ROW, column=idx).alignment = WRAP
        h = ws.cell(row=HEADER_ROW, column=idx, value=header + ("*" if required else ""))
        h.font = HEADER_REQUIRED_FONT if required else HEADER_FONT
        h.alignment = WRAP

    # --- Выпадающие списки из спека (Цвет / Размер и другие совпадающие по имени) ---
    spec_values: dict[str, list] = {}
    for a in (spec or {}).get("attributes") or []:
        if a.get("name") and a.get("values"):
            spec_values.setdefault(_norm(a["name"]), a["values"])

    for header, required, _hint, key in AE_MAIN_COLUMNS + AE_SKU_COLUMNS:
        values = spec_values.get(_norm(header))
        if not values or len(values) < 2:
            continue
        col_idx = _column_index(header, sku_start)
        letter = get_column_letter(col_idx)
        if len(values) <= 8 and all(len(str(v)) < 20 for v in values):
            dv = DataValidation(
                type="list",
                formula1='"' + ",".join(str(v) for v in values) + '"',
                allow_blank=True,
            )
            ws.add_data_validation(dv)
            dv.add(f"{letter}{DATA_START_ROW}:{letter}{last_row}")
        else:
            title = _add_dict_sheet(wb, f"Список {header}", used_dicts)
            n = _fill_dict_sheet(wb, title, values)
            dv = DataValidation(
                type="list", formula1=f"'{title}'!$A$1:$A${n}", allow_blank=True
            )
            ws.add_data_validation(dv)
            dv.add(f"{letter}{DATA_START_ROW}:{letter}{last_row}")

    # --- Данные ---
    for r, values in enumerate(rows_values, start=DATA_START_ROW):
        for col, (_header, _req, _hint, key) in enumerate(AE_MAIN_COLUMNS, start=1):
            _write_cell(ws, r, col, values.get(key))
        for idx, name in enumerate(custom_names):
            _write_cell(ws, r, custom_start + idx, values.get(_norm(name)))
        for idx, (_header, _req, _hint, key) in enumerate(
            AE_SKU_COLUMNS, start=sku_start
        ):
            _write_cell(ws, r, idx, values.get(key))

    # --- Ширины колонок, высоты строк шапки и закрепление шапки ---
    for col, (header, _req, _hint, _key) in enumerate(AE_MAIN_COLUMNS, start=1):
        _set_width(ws, col, header)
    for col in range(custom_start, sku_start):
        _set_width(ws, col, "Произвольная характеристика")
    for col, (header, _req, _hint, _key) in enumerate(AE_SKU_COLUMNS, start=sku_start):
        _set_width(ws, col, header)
    _fit_header_heights(ws)
    ws.freeze_panes = f"A{DATA_START_ROW}"

    _build_instruction_sheet(wb)
    _build_images_sheet(wb)
    return wb


# ==================== Демо-пример из официальной документации ====================


def aliexpress_example_products() -> list[dict]:
    """
    Демо-товар из скриншота официального шаблона: свитер с вариациями
    цветов (Красный / Белый) и размеров (S / M) — 4 строки SKU.
    """
    return [
        {
            "id": 1,
            "sku": "SW01",
            "name": "Свитер вязаный хлопковый оверсайз",
            "price": 2490,
            "stock": 15,
            "description": "Тёплый свитер из натурального хлопка, подходит для повседневной носки.",
            "brand": "NONE",
            "barcode": "3545345",
            "category": "Одежда / Свитеры и кофты",
            "photos": [
                "https://example.ru/upload/sweater_main.jpg",
                "https://example.ru/upload/sweater_2.jpg",
            ],
            "package_weight_grams": 450,
            "package_length_mm": 300,
            "package_width_mm": 250,
            "package_height_mm": 50,
            "variants": [
                {"sku": "32423535", "barcode": "3545345", "color": "Красный", "size": "S", "stock": 5, "price": 2490},
                {"sku": "32423536", "barcode": "3545347", "color": "Белый", "size": "M", "stock": 4, "price": 2490},
                {"sku": "32423537", "barcode": "3545348", "color": "Красный", "size": "M", "stock": 3, "price": 2490},
                {"sku": "32423538", "barcode": "3545349", "color": "Белый", "size": "S", "stock": 3, "price": 2490},
            ],
            "attributes": [
                {"name": "Сезон", "value": "Демисезон"},
                {"name": "Состав", "value": "50% хлопок, 50% акрил"},
            ],
        }
    ]


# ==================== Служебные ====================


def _column_index(header: str, sku_start: int) -> int:
    for col, (h, *_rest) in enumerate(AE_MAIN_COLUMNS, start=1):
        if h == header:
            return col
    for idx, (h, *_rest) in enumerate(AE_SKU_COLUMNS, start=sku_start):
        if h == header:
            return idx
    return 1


def _count_lines(text: str, width: float) -> int:
    """Оценка числа строк текста при переносе по заданной ширине колонки."""
    if not text:
        return 1
    # Коэффициент 0.95 — с запасом на рендер Liberation Sans / Arial в Excel и LibreOffice
    chars_per_line = max(int((width or 18) * 0.95), 8)
    lines = 0
    for part in str(text).split("\n"):
        lines += max(1, math.ceil(len(part) / chars_per_line))
    return lines


def _fit_header_heights(ws) -> None:
    """Подгоняет высоты строк блоков/подсказок/заголовков, чтобы текст не обрезался."""
    ws.row_dimensions[BLOCK_ROW].height = 32

    hint_lines = 1
    header_lines = 1
    for col in range(1, ws.max_column + 1):
        letter = get_column_letter(col)
        width = ws.column_dimensions[letter].width or 18
        hint_val = ws.cell(row=HINT_ROW, column=col).value
        if hint_val:
            hint_lines = max(hint_lines, _count_lines(str(hint_val), width))
        header_val = ws.cell(row=HEADER_ROW, column=col).value
        if header_val:
            header_lines = max(header_lines, _count_lines(str(header_val), width))
    ws.row_dimensions[HINT_ROW].height = max(34, hint_lines * 12 + 6)
    ws.row_dimensions[HEADER_ROW].height = max(18, header_lines * 14)


def _write_cell(ws, row: int, col: int, value) -> None:
    if value in (None, ""):
        return
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = DATA_FONT


def _set_width(ws, col: int, header: str) -> None:
    letter = get_column_letter(col)
    if "фото" in header.lower() or "ссылк" in header.lower():
        width = 34
    elif "seller" in header.lower() or len(header) > 24:
        width = 26
    else:
        width = 18
    ws.column_dimensions[letter].width = width


def _build_instruction_sheet(wb: Workbook) -> None:
    """Лист «Инструкция»: правила заполнения из официальной документации AliExpress."""
    ws = wb.create_sheet("Инструкция")
    lines = [
        "Загрузка товаров через Excel — AliExpress",
        "",
        "ПЕРЕД ЗАГРУЗКОЙ ТОВАРОВ",
        "1. Создайте шаблон доставки.",
        "2. Зарегистрируйте бренды товаров.",
        "3. Подайте заявку с подтверждающими документами, если продаёте товары "
        "в специальных категориях (например, товары для взрослых или ювелирные изделия).",
        "",
        "КАК ЗАПОЛНИТЬ ШАБЛОН",
        "• Пользуйтесь подсказками над полями — там указаны допустимые значения, "
        "например, диапазон или максимальная длина текста.",
        "• Не меняйте структуру шаблона — не добавляйте, не удаляйте и не перемещайте столбцы.",
        "• Заполните все обязательные поля — они отмечены звёздочкой (*).",
        "• В ячейках с выпадающими списками используйте только выбор из списка, "
        "не вписывайте значения вручную.",
        "• «Только целые значения» — числа 0–9999999 без единиц измерения.",
        "• «Только цифры» — числа 0,0–9999999,99 без единиц измерения.",
        "• Вес, цена и габариты не могут быть равны нулю.",
        "",
        "ВАРИАЦИИ ТОВАРА (НЕСКОЛЬКО ЦВЕТОВ / РАЗМЕРОВ)",
        "• В колонке «Модель (seller SPU ID)» укажите одинаковое значение для всех вариаций "
        "одного товара — они объединятся в одну карточку.",
        "• В колонке «Артикул/Штрихкод (seller SKU ID)» укажите уникальный артикул "
        "для каждой вариации.",
        "• В блоке «Информация о модификации товара (SKU)» задайте уникальные значения "
        "характеристик (Цвет, Размер) для каждой вариации.",
        "• Пример: юбка красного и серого цветов, размеров S и M — создайте 4 вариации "
        "(красный S, красный M, серый S, серый M).",
        "• В вариациях не учитываются поля «Название цвета в системе продавца» и "
        "«Название размера в системе продавца»: если для двух товаров указан одинаковый "
        "Цвет (например, красный), это будет одна вариация, даже если ваши названия "
        "разные (алый и бордовый).",
        "",
        "ПРОИЗВОЛЬНЫЕ ХАРАКТЕРИСТИКИ ПРОДАВЦА",
        "• До пяти характеристик в блоке «Произвольные характеристики продавца»: "
        "в строке заголовков укажите название характеристики, а в строках товаров — "
        "любое значение.",
        "",
        "КАК ЗАГРУЗИТЬ ШАБЛОН",
        "1. В личном кабинете: Товары → Массовые операции Excel → Загрузить.",
        "2. В форме «Загрузка товаров» выберите категорию и скачайте шаблон категории "
        "(в один шаблон можно загрузить товары только из одной категории).",
        "3. Заполните файл и загрузите его в форме «Загрузка товаров».",
        "4. После загрузки появится отчёт: если в колонке «Незагруженные» ненулевое "
        "значение — скачайте файл с ошибками, исправьте выделенные поля и загрузите "
        "файл заново.",
        "5. После загрузки товары отправятся на модерацию (до 48 часов, иногда до "
        "7 дней). Затем они появятся на вкладке «В продаже».",
        "",
        "ВАЖНО",
        "• Официальный шаблон из кабинета уже содержит ваши метаданные — не изменяйте "
        "их и не стирайте существующие значения.",
        "• Не копируйте данные из шаблонов других категорий (кроме ссылок на "
        "изображения и значений цен).",
    ]
    _fill_text_sheet(ws, lines)


def _build_images_sheet(wb: Workbook) -> None:
    """Лист «Требования к изображениям» — из официальной документации AliExpress."""
    ws = wb.create_sheet("Требования к изображениям")
    lines = [
        "Требования к изображениям",
        "",
        "ССЫЛКА НА ИЗОБРАЖЕНИЕ ДОЛЖНА:",
        "• вести на само изображение (JPG/PNG), а не на страницу с изображением;",
        "• быть прямой и рабочей (проверьте открытие ссылки в браузере);",
        "• вести на открытый источник, а не на закрытые облачные хранилища "
        "(Облако Mail.ru, Google Drive, Яндекс Диск);",
        "• соответствовать требованиям к файлам: формат JPEG/PNG, разрешение "
        "от 200 px по меньшей стороне, размер до 10 МБ.",
        "",
        "КАК ПОЛУЧИТЬ ПРЯМУЮ ССЫЛКУ НА ИЗОБРАЖЕНИЕ:",
        "1. Откройте страницу с изображением на вашем сервере.",
        "2. Наведите курсор на изображение и нажмите правую кнопку мыши.",
        "3. Выберите действие в зависимости от браузера:",
        "   Chrome — «Копировать URL картинки».",
        "   Safari — «Скопировать адрес изображения».",
        "   Firefox — «Копировать ссылку на изображение».",
        "",
        "ПРИМЕР ПРЯМОЙ ССЫЛКИ: https://i.ibb.co/sHTX5yv/1.png",
    ]
    _fill_text_sheet(ws, lines)


def _fill_text_sheet(ws, lines: list[str], width: float = 88) -> None:
    """Одноколоночный текстовый лист с переносом, явными высотами строк и вписыванием по ширине страницы."""
    from openpyxl.worksheet.properties import PageSetupProperties

    for r, text in enumerate(lines, start=1):
        cell = ws.cell(row=r, column=1, value=text or None)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if r == 1 or (text and text == text.upper() and len(text) > 3 and "«" not in text):
            cell.font = Font(name="Arial", size=12 if r == 1 else 10, bold=True)
        else:
            cell.font = Font(name="Arial", size=10)
        if text:
            ws.row_dimensions[r].height = max(15, _count_lines(text, width) * 13.5 + 3)
    ws.column_dimensions["A"].width = width
    # Вписываем лист в ширину одной страницы при печати/экспорте в PDF
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

