"""
Билдер книги Мегамаркета (СберМегамаркет): структура Excel-файла с ассортиментом
(раздел «Товары и цены → Загрузка и обновление → Excel» базы знаний Мегамаркета).

Лист «Товары»: строка 1 — заголовки колонок (обязательные отмечены звёздочкой *),
строка 2+ — данные (одна строка = один товар / offer).

Правила площадки (из документации и подтверждённой выжимки):
  • в «Код товара продавца» запрещены символы # и %;
  • основной штрихкод (GTIN) — EAN-13, не может начинаться с 2;
  • десятичные дроби (вес, габариты) пишутся через запятую,
    не более 2 знаков после запятой;
  • до 10 фото (URL основного фото + URL фото 2…10);
  • соседняя вкладка — инструкция с примерами.
"""

import math

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from services.template_filler import (
    _build_enum_fix,
    _expand_products_for_platform,
    _row_values,
)

HEADER_ROW = 1
DATA_START_ROW = 2

# ==================== Колонки: (заголовок, обязательная, ключ значений) ====================

MM_COLUMNS = [
    ("Код товара продавца", True, "кодтоварапродавца"),
    ("Основной штрихкод (GTIN)", True, "основнойштрихкодgtin"),
    ("Штрихкод 2", False, "штрихкод2"),
    ("Штрихкод 3", False, "штрихкод3"),
    ("Штрихкод 4", False, "штрихкод4"),
    ("Штрихкод 5", False, "штрихкод5"),
    ("Ссылка на pdf-инструкцию", False, "ссылканаpdfинструкцию"),
    ("Ссылка на сертификат", False, "ссылканасертификат"),
    (
        "Название товара по формуле: Тип товара+Бренд+Модель/Артикул",
        True,
        "названиетоварапоформулетиптоварабрендмодельартикул",
    ),
    ("Описание товара", True, "описаниетовара"),
    ("Бренд", False, "бренд"),
    ("Модель", False, "модель"),
    ("Артикул производителя", False, "артикулпроизводителя"),
    ("НДС", False, "ндс"),
    ("Цена", True, "цена"),
    ("Вес, кг", True, "вескг"),
    ("Длина, см", True, "длинасм"),
    ("Ширина, см", True, "ширинасм"),
    ("Высота, см", True, "высотасм"),
    ("URL основного фото", True, "urlосновногофото"),
    ("URL фото 2", False, "urlфото2"),
    ("URL фото 3", False, "urlфото3"),
    ("URL фото 4", False, "urlфото4"),
    ("URL фото 5", False, "urlфото5"),
    ("URL фото 6", False, "urlфото6"),
    ("URL фото 7", False, "urlфото7"),
    ("URL фото 8", False, "urlфото8"),
    ("URL фото 9", False, "urlфото9"),
    ("URL фото 10", False, "urlфото10"),
]

VAT_VALUES = ["Не облагается", "22", "10", "7", "5"]

HEADER_FONT = Font(name="Arial", size=10, bold=True)
HEADER_REQUIRED_FONT = Font(name="Arial", size=10, bold=True, color="C00000")
HEADER_FILL = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
DATA_FONT = Font(name="Arial", size=10)


# ==================== Публичные функции ====================


def megamarket_flat_rows(products: list, spec: dict | None = None) -> list[dict]:
    """Плоские строки (заголовок → значение) для предпросмотра выгрузки."""
    expanded = _expand_products_for_platform(products, "megamarket")
    enum_fix = _build_enum_fix(spec)
    rows: list[dict] = []
    for i, p in enumerate(expanded, start=1):
        values = _row_values(p, i, enum_fix, platform="megamarket")
        row = {header: values.get(key) for header, _req, key in MM_COLUMNS}
        rows.append(row)
    return rows


def build_megamarket_workbook(products: list, spec: dict | None = None) -> Workbook:
    """Собирает книгу в структуре Excel-файла с ассортиментом Мегамаркета."""
    expanded = _expand_products_for_platform(products, "megamarket")
    enum_fix = _build_enum_fix(spec)
    rows_values = [
        _row_values(p, i, enum_fix, platform="megamarket")
        for i, p in enumerate(expanded, start=1)
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "Товары"

    last_row = max(DATA_START_ROW + len(rows_values) - 1, DATA_START_ROW) + 50

    # --- Строка 1: заголовки ---
    for col, (header, required, _key) in enumerate(MM_COLUMNS, start=1):
        cell = ws.cell(row=HEADER_ROW, column=col, value=header + ("*" if required else ""))
        cell.font = HEADER_REQUIRED_FONT if required else HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")

    # --- Выпадающий список для НДС ---
    vat_col = next(
        col for col, (h, _r, _k) in enumerate(MM_COLUMNS, start=1) if h == "НДС"
    )
    letter = get_column_letter(vat_col)
    dv = DataValidation(
        type="list", formula1='"' + ",".join(VAT_VALUES) + '"', allow_blank=True
    )
    ws.add_data_validation(dv)
    dv.add(f"{letter}{DATA_START_ROW}:{letter}{last_row}")

    # --- Данные ---
    for r, values in enumerate(rows_values, start=DATA_START_ROW):
        for col, (_header, _req, key) in enumerate(MM_COLUMNS, start=1):
            val = values.get(key)
            if val in (None, ""):
                continue
            cell = ws.cell(row=r, column=col, value=val)
            cell.font = DATA_FONT

    # --- Ширины колонок, высота шапки и закрепление ---
    for col, (header, _req, _key) in enumerate(MM_COLUMNS, start=1):
        letter = get_column_letter(col)
        if "URL" in header or "Ссылка" in header:
            width = 34
        elif len(header) > 24:
            width = 28
        else:
            width = 16
        ws.column_dimensions[letter].width = width

    header_lines = 1
    for col, (header, _req, _key) in enumerate(MM_COLUMNS, start=1):
        letter = get_column_letter(col)
        width = ws.column_dimensions[letter].width or 18
        header_lines = max(header_lines, _count_lines(header, width))
    ws.row_dimensions[HEADER_ROW].height = max(18, header_lines * 13)
    ws.freeze_panes = f"A{DATA_START_ROW}"

    _build_instruction_sheet(wb)
    return wb


# ==================== Демо-пример ====================


def megamarket_example_products() -> list[dict]:
    """Демо-товар для скачиваемого шаблона Мегамаркета."""
    return [
        {
            "id": 1001,
            "sku": "SMM-1001",
            "name": "Кофемашина DeLonghi Magnifica ECAM22.110",
            "price": 34990,
            "stock": 10,
            "description": (
                "Автоматическая кофемашина с капучинатором и встроенной кофемолкой."
            ),
            "brand": "DeLonghi",
            "barcode": "4600000010018",
            "category": "Техника для кухни / Кофемашины",
            "photos": [
                "https://example.com/coffee1.jpg",
                "https://example.com/coffee2.jpg",
            ],
            "package_weight_grams": 9500,
            "package_length_mm": 430,
            "package_width_mm": 240,
            "package_height_mm": 350,
            "vat_rate": "none",
            "attributes": [
                {"name": "Модель", "value": "Magnifica ECAM22.110"},
            ],
        }
    ]


# ==================== Служебные ====================


def _count_lines(text: str, width: float) -> int:
    """Оценка числа строк текста при переносе по заданной ширине колонки."""
    if not text:
        return 1
    # Коэффициент 0.95 — с запасом на рендер Liberation Sans / Arial в Excel и LibreOffice
    chars_per_line = max(int((width or 18) * 0.95), 8)
    return max(1, math.ceil(len(str(text)) / chars_per_line))


def _fill_text_sheet(ws, lines: list[str], width: float = 88) -> None:
    """Одноколоночный текстовый лист с переносом, явными высотами строк и вписыванием по ширине страницы."""
    from openpyxl.worksheet.properties import PageSetupProperties

    for r, text in enumerate(lines, start=1):
        cell = ws.cell(row=r, column=1, value=text or None)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        is_section = bool(text) and text == text.upper() and len(text) > 3 and "«" not in text
        cell.font = Font(name="Arial", size=12 if r == 1 else 10, bold=(r == 1 or is_section))
        if text:
            ws.row_dimensions[r].height = max(15, _count_lines(text, width) * 13.5 + 3)
    ws.column_dimensions["A"].width = width
    # Вписываем лист в ширину одной страницы при печати/экспорте в PDF
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0


def _build_instruction_sheet(wb: Workbook) -> None:
    """Лист «Инструкция» — правила заполнения файла с ассортиментом Мегамаркета."""
    ws = wb.create_sheet("Инструкция")
    lines = [
        "Мегамаркет: добавление и изменение товаров с помощью Excel-файла",
        "",
        "КАК ЗАГРУЗИТЬ ТОВАРЫ",
        "1. Заполните лист «Товары» (одна строка — один товар).",
        "2. В личном кабинете: Товары и цены → Загрузка и обновление → Excel.",
        "3. Добавьте файл и нажмите «Загрузить». Максимальный размер — 500 МБ "
        "(если больше — используйте XML-формат).",
        "4. Загруженные товары появятся на вкладке «Сводка по ассортименту» в течение "
        "нескольких минут или часов, затем свяжите товары с карточками Мегамаркета.",
        "",
        "ПРАВИЛА ЗАПОЛНЕНИЯ",
        "• Не меняйте структуру файла: не добавляйте, не удаляйте и не переименовывайте "
        "столбцы и листы.",
        "• «Код товара продавца» — уникальный код товара в вашей системе; "
        "запрещены символы # и %.",
        "• «Основной штрихкод (GTIN)» — 13-значный штрихкод EAN-13/UCC-13; "
        "штрихкоды, начинающиеся с 2, не принимаются.",
        "• Десятичные дроби (вес и габариты) пишутся через запятую, "
        "не более 2 знаков после запятой. Пример: 9,5.",
        "• «Название товара по формуле: Тип товара+Бренд+Модель/Артикул» — "
        "название строится из типа товара, бренда и модели/артикула.",
        "• «НДС» — выберите значение из списка.",
        "• «Цена» — число без символов валют.",
        "• Фото — прямые HTTPS-ссылки на изображение (не страницы и не закрытые "
        "облачные хранилища). До 10 фото: «URL основного фото» и «URL фото 2–10».",
        "",
        "КАК ОБНОВИТЬ ДАННЫЕ",
        "• Скачайте исходный файл в кабинете, измените его и загрузите заново — "
        "товары обновятся по «Коду товара продавца».",
        "• Можно пользоваться только одним способом загрузки: если начали с Excel — "
        "продолжайте в Excel.",
        "• Чтобы товар перестал отображаться — удалите его из файла и загрузите "
        "обновлённый файл.",
    ]
    _fill_text_sheet(ws, lines)
