"""
Генератор XLSX v2: файлы, СТРУКТТУРНО идентичные реальным шаблонам площадок.

Эталон Ozon (файлы от 23.09.2026: «Адаптер для зарядки электромобиля», «Бабочка»):
  Лист «Шаблон»:
    строка 1 — группы-блоки («Название», «Заполняйте только при создании…», …)
    строка 2 — названия колонок, обязательные со звёздочкой: «Артикул*»
    строка 3 — маркеры: «Обязательное поле», «Ⓜ️ Множественный выбор»,
               «Ⓜ️ Не более N вариантов», «ϟ  Влияет на продвижение»
    строка 4 — подсказки со ссылками на seller-edu.ozon.ru
    строка 5+ — данные товаров
  Листы (порядок важен): «Озон.Видео», «Озон.Видеообложка», «Документация PDF»
  Служебные колонки в конце: «Ошибка», «Недочёты»

Правила значений:
- числа без единиц измерения;
- множественный выбор через «;» без пробелов;
- регистр значений из словаря соблюдается (защита от дублей карточек);
- выбор из списка — data validation Excel (большие словари на скрытых листах);
- дубли артикулов получают суффиксы _2, _3 (Ozon не принимает дубли).
"""
import io
import re
import zipfile
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
HEADER_FONT = Font(bold=True)
DICT_LIMIT = 5000

DATA_START_ROW = 5          # данные начинаются с 5-й строки (как в шаблоне Ozon)

VAT_LABELS = {"none": "Не облагается", "22": "22", "10": "10", "7": "7", "5": "5"}

GROUP_ORDER = ["brand", "variant", "common", "additional", "fits_for"]

# Тексты групп-блоков для строки 1
G_NAME = "Название"
G_PRICE = ("Заполняйте только при создании нового товара. Изменить цену существующего товара "
           "можно в разделе «Цены и акции → Обновить цены»")
G_CONVERT = "Самые популярные способы поднять конверсию"
G_SKU = "Блок можно не заполнять, если товар продается на Ozon и вы заполнили поле SKU"
G_INFO = ("Блок можно не заполнять, если товар продается на Ozon и вы заполнили либо поле SKU, "
          'либо блок "Информация о товаре"')
G_UNION = ("Для всех вариантов товара, которые вы хотите объединить на одной карточке, "
           "укажите одинаковые значения в этих полях")
G_VARIANT = ("Вы можете заполнить эти поля как одинаковыми значениями (если в этой характеристике "
             "вариант не отличается от других) или разными (если отличается)")

BRAND_NAMES = {"бренд", "бренд в одежде и обуви"}

# ==================== Базовые колонки Ozon (эталон 23.09.2026) ====================
# (заголовок, ключ, обязательное, тип, подсказка, группа-блок строки 1)
OZON_BASE_COLUMNS = [
    ("№", "_row_num", False, "number", "", ""),
    ("Артикул", "article", True, "text",
     "Введите артикул товара или его номер в вашей базе. Артикул должен быть уникальным "
     "в рамках вашего ассортимента "
     "https://seller-edu.ozon.ru/docs/work-with-goods/trebovaniya-k-kartochkam-tovarov/articyl-tovara.html", ""),
    ("Название товара", "name", False, "text",
     "Вы можете не заполнять это поле — тогда название составится автоматически из обязательных "
     "характеристик: тип + бренд + модель + важные характеристики "
     "https://seller-edu.ozon.ru/libra/work-with-goods/trebovaniya-k-kartochkam-tovarov/product-information/nazvanie-tovara",
     G_NAME),
    ("Предельная цена без акций, руб.", "price", True, "number",
     "Цена, которую вы устанавливаете вручную "
     "https://seller-edu.ozon.ru/libra/ceny-i-akcii/rabota-s-cenami/price-control", G_PRICE),
    ("Зачёркнутая цена, руб.", "strike_price", False, "number",
     "Цена, которую покупатель видит зачёркнутой "
     "https://seller-edu.ozon.ru/libra/ceny-i-akcii/rabota-s-cenami/price-control", G_PRICE),
    ("НДС, %", "vat_rate", True, "select",
     "Укажите ставку НДС. Если товар не облагается НДС, или вы не платите НДС – укажите Не облагается "
     "https://seller-edu.ozon.ru/libra/work-with-goods/zagruzka-tovarov/creating-goods/sozdanie-tovarov-v-lk",
     G_PRICE),
    ("Рассрочка", "installment", False, "select",
     "Добавим товару пометку «Рассрочка 0–0–6» и будем отображать в специальных подборках. "
     "Дисконт удерживается только за проданные товары вместе с другими комиссиями, "
     "а Ozon сразу переводит вам полную стоимость товара.", G_CONVERT),
    ("Ускоренный сбор отзывов", "reviews_boost", False, "select",
     "Подключим товару ускоренный сбор отзывов. Вы получите 10 отзывов с любым контентом: текст, фото, "
     "видео, или просто оценки. Стоимость за один отзыв или оценку — 250 ₽.", G_CONVERT),
    ("SKU", "sku_copy", False, "text",
     "Заполните поле, если хотите скопировать чужой товар, размещённый на Ozon. "
     "Тогда блоки справа можно не заполнять. Артикул должен быть уникальным. "
     "https://seller-edu.ozon.ru/libra/work-with-goods/zagruzka-tovarov/created-goods/uznat-sku-tovarov",
     G_SKU),
    ("Штрихкод (Серийный номер / EAN)", "barcode", False, "text",
     "Введите штрихкод товара от производителя и наклейте его на упаковку. Это код, по которому товар "
     "принимают на складе. Поле обязательно для всех схем продаж. Без штрихкода не сможем выплатить "
     "компенсацию при утере "
     "https://seller-edu.ozon.ru/work-with-goods/trebovaniya-k-kartochkam-tovarov/product-information/rabota-so-shtrihkodami",
     G_SKU),
    ("ТН ВЭД коды ЕАЭС", "okpd_code", True, "select",
     "Выберите одно значение из списка. Если вы не знаете, какой код нужно указать, "
     "то вам необходимо обратиться к таможенной службе или таможенному представителю.", G_INFO),
    ("Вес в упаковке, г", "package_weight_grams", True, "number",
     "Можем взять дополнительную плату, если ОВХ отличаются от реальных. Укажите вес единицы товара "
     "в граммах вместе с упаковкой, в которой будете отправлять товар. Введите только число "
     "https://seller-edu.ozon.ru/libra/work-with-goods/trebovaniya-k-kartochkam-tovarov/product-information/ovh",
     G_INFO),
    ("Ширина упаковки, мм", "package_width_mm", True, "number",
     "Можем взять дополнительную плату, если ОВХ отличаются от реальных. Измерьте в миллиметрах любую "
     "сторону товара в упаковке. Введите только число "
     "https://seller-edu.ozon.ru/docs/work-with-goods/trebovaniya-k-kartochkam-tovarov/ovh.html", G_INFO),
    ("Высота упаковки, мм", "package_height_mm", True, "number",
     "Можем взять дополнительную плату, если ОВХ отличаются от реальных. Измерьте в миллиметрах любую "
     "сторону товара в упаковке. Введите только число "
     "https://seller-edu.ozon.ru/docs/work-with-goods/trebovaniya-k-kartochkam-tovarov/ovh.html", G_INFO),
    ("Длина упаковки, мм", "package_length_mm", True, "number",
     "Можем взять дополнительную плату, если ОВХ отличаются от реальных. Измерьте в миллиметрах любую "
     "сторону товара в упаковке. Введите только число "
     "https://seller-edu.ozon.ru/docs/work-with-goods/trebovaniya-k-kartochkam-tovarov/ovh.html", G_INFO),
    ("Ссылка на главное фото", "main_photo", True, "text",
     "Прямая ссылка на изображение (jpeg, jpg, png). Только одна ссылка — лишние не будут использованы. "
     "По ссылке должны открываться и скачиваться только сами изображения "
     "https://seller-edu.ozon.ru/work-with-goods/trebovaniya-k-kartochkam-tovarov/media/foto-i-video-tovara",
     G_INFO),
    ("Ссылки на дополнительные фото", "extra_photos", False, "text",
     "До 14 ссылок, разделённых пробелом или переносом строки. По ссылкам должны открываться "
     "и скачиваться только сами изображения.", G_INFO),
    ("Артикул фото", "photo_article", False, "text",
     'Название файла с изображением товара. Запрещенные символы: "/" и "_".', G_INFO),
]


# ========== Вспомогательные ==========

def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Zа-яА-Я]+", "_", name).strip("_")[:40] or "category"


def _match_enum_case(value: str, values: list) -> str:
    """Подбираем точный регистр значения из словаря площадки (защита от дублей)."""
    low = (value or "").strip().lower()
    for v in values or []:
        if str(v).strip().lower() == low:
            return str(v)
    return (value or "").strip()


def _normalize_multi(value: str) -> str:
    """Приводим множественные значения к формату Ozon: «белый;голубой» (без пробелов)."""
    parts = re.split(r"[;,]", value or "")
    return ";".join(p.strip() for p in parts if p.strip())


def _attr_value(product: dict, attr_name: str) -> Optional[str]:
    for a in product.get("attributes") or []:
        if (a.get("name") or "").strip().lower() == attr_name.strip().lower():
            return a.get("value")
    return None


def _add_dict_sheet(wb: Workbook, attr_name: str, used: dict) -> str:
    """Скрытый лист со словарём значений для data validation."""
    base = f"dict_{_slug(attr_name)}"[:28]
    title = base
    i = 1
    while title in used:
        title = f"{base[:26]}_{i}"
        i += 1
    used[title] = True
    wb.create_sheet(title)
    return title


def _fill_dict_sheet(wb: Workbook, title: str, values: list) -> int:
    ws = wb[title]
    n = 0
    for row, v in enumerate(values[:DICT_LIMIT], start=1):
        ws.cell(row=row, column=1, value=str(v))
        n = row
    ws.sheet_state = "hidden"
    return n


def _is_brand(attr: dict) -> bool:
    return (attr.get("name") or "").strip().lower() in BRAND_NAMES


def _attr_group_text(attr: dict) -> str:
    """Текст группы-блока (строка 1) для атрибутной колонки."""
    name = (attr.get("name") or "").lower()
    if _is_brand(attr) or "объедин" in name:
        return G_UNION
    return G_VARIANT


def _row3_marker(col: dict) -> Optional[str]:
    """Маркер строки 3 по правилам реального шаблона."""
    if col["multi"]:
        if col.get("max_count"):
            return f"Ⓜ️ Не более {col['max_count']} вариантов"
        return "Ⓜ️ Множественный выбор"
    if col.get("is_brand"):
        return "ϟ  Влияет на продвижение"
    if col["required"]:
        return "Обязательное поле"
    return None


def _unique_articles(products: list) -> None:
    """
    Уникализация артикулов in-place: дубли получают суффиксы _2, _3.
    Правило Ozon: «Если в вашей базе артикулы повторяются, сделайте их уникальными».
    """
    seen = {}
    for p in products:
        base = (p.get("sku") or p.get("external_id") or f"ID{p.get('id')}")
        count = seen.get(base, 0) + 1
        seen[base] = count
        p["_article"] = base if count == 1 else f"{base}_{count}"


# ========== Значения ячеек ==========

def _ozon_cell_value(product: dict, col: dict, row_num: int):
    key = col["key"]
    if key is None:
        return None
    if key == "_row_num":
        return row_num
    if key == "article":
        return product.get("_article") or product.get("sku") or product.get("external_id") or f"ID{product.get('id')}"
    if key == "name":
        return product.get("name")
    if key == "price":
        return product.get("price")
    if key == "strike_price":
        return product.get("strike_price")
    if key == "vat_rate":
        return VAT_LABELS.get(str(product.get("vat_rate") or ""), product.get("vat_rate"))
    if key == "barcode":
        return _normalize_multi(product.get("barcode") or "") or None
    if key == "okpd_code":
        return product.get("okpd_code")
    if key in ("package_weight_grams", "package_width_mm", "package_height_mm",
               "package_length_mm", "units_per_item"):
        return product.get(key)
    if key == "main_photo":
        photos = product.get("photos") or []
        return photos[0] if photos else None
    if key == "extra_photos":
        photos = product.get("photos") or []
        return " ".join(photos[1:15]) if len(photos) > 1 else None
    if key == "photo_article":
        return product.get("photo_article")
    if key.startswith("attr:"):
        attr_name = key[5:]
        raw = _attr_value(product, attr_name)
        if raw is None or raw == "":
            return None
        if col["multi"]:
            return _normalize_multi(str(raw))
        if col["values"]:
            return _match_enum_case(str(raw), col["values"])
        if col["type"] == "number":
            try:
                v = float(raw)
                return int(v) if v == int(v) else v
            except (TypeError, ValueError):
                return raw
        return str(raw)
    return None


# ========== Сборка книги Ozon ==========

def build_ozon_workbook(products: list, spec: Optional[dict]) -> Workbook:
    """
    Файл, структурно идентичный XLS-шаблону Ozon от 23.09.2026:
    строки 1-4 — шапка (блоки / названия* / маркеры / подсказки), данные с строки 5.
    """
    # ✅ Уникализация артикулов ДО построения плана
    _unique_articles(products)

    wb = Workbook()
    ws = wb.active
    ws.title = "Шаблон"

    attributes = (spec or {}).get("attributes") or []
    attributes = sorted(
        attributes,
        key=lambda a: GROUP_ORDER.index(a.get("group", "common"))
        if a.get("group", "common") in GROUP_ORDER else 99,
    )

    # ---------- План колонок: база + атрибуты спека + служебные ----------
    columns = []
    for header, key, required, ctype, hint, group in OZON_BASE_COLUMNS:
        columns.append({
            "header": header, "key": key, "required": required, "type": ctype,
            "hint": hint, "group": group, "values": None, "multi": False,
            "max_count": None, "is_brand": False,
        })
    for col in columns:
        if col["key"] == "vat_rate":
            col["values"] = ["Не облагается", "22", "10", "7", "5"]
        if col["key"] in ("installment", "reviews_boost"):
            col["values"] = ["Да", "Нет"]

    for a in attributes:
        columns.append({
            "header": a["name"],
            "key": f"attr:{a['name']}",
            "required": bool(a.get("required")),
            "type": a.get("type", "text"),
            "hint": a.get("description") or "",
            "group": _attr_group_text(a),
            "values": a.get("values"),
            "multi": a.get("type") == "multiselect",
            "max_count": a.get("max_count"),
            "is_brand": _is_brand(a),
        })

    columns.append({
        "header": "Ошибка", "key": None, "required": False, "type": "text",
        "hint": "Критичная ошибка в характеристиках товара. Товар с ошибками не будет продаваться.",
        "group": "", "values": None, "multi": False, "max_count": None, "is_brand": False,
    })
    columns.append({
        "header": "Недочёты", "key": None, "required": False, "type": "text",
        "hint": "Устаревшее или незаполненное значение в характеристиках товара. "
                "Возникает при изменениях в атрибутной модели и не влияет на продажу товара.",
        "group": "", "values": None, "multi": False, "max_count": None, "is_brand": False,
    })

    used_dicts = {}
    last_row = max(DATA_START_ROW + len(products) - 1, DATA_START_ROW) + 50

    # ---------- 4 строки шапки ----------
    for idx, col in enumerate(columns, start=1):
        letter = get_column_letter(idx)

        # строка 1: группа-блок
        ws.cell(row=1, column=idx, value=col["group"] or None)

        # строка 2: название (+ '*' у обязательных), красная заливка
        c2 = ws.cell(row=2, column=idx, value=col["header"] + ("*" if col["required"] else ""))
        c2.font = HEADER_FONT
        if col["required"]:
            c2.fill = RED_FILL

        # строка 3: маркеры
        ws.cell(row=3, column=idx, value=_row3_marker(col))

        # строка 4: подсказка
        hint = col["hint"]
        if not hint and col["values"]:
            hint = "Выберите значение из списка. Примеры: " + "; ".join(str(v) for v in col["values"][:5])
        ws.cell(row=4, column=idx, value=hint or None)

        # data validation для списков (диапазон данных)
        if col["values"]:
            rng = f"{letter}{DATA_START_ROW}:{letter}{last_row}"
            if len(col["values"]) <= 8 and all(len(str(v)) < 20 for v in col["values"]):
                dv = DataValidation(
                    type="list",
                    formula1='"' + ",".join(str(v) for v in col["values"]) + '"',
                    allow_blank=True,
                )
                ws.add_data_validation(dv)
                dv.add(rng)
            else:
                title = _add_dict_sheet(wb, col["header"], used_dicts)
                n = _fill_dict_sheet(wb, title, col["values"])
                dv = DataValidation(type="list", formula1=f"'{title}'!$A$1:$A${n}", allow_blank=True)
                ws.add_data_validation(dv)
                dv.add(rng)

    # ---------- Данные с 5-й строки ----------
    for r, product in enumerate(products, start=DATA_START_ROW):
        for idx, col in enumerate(columns, start=1):
            value = _ozon_cell_value(product, col, row_num=r - DATA_START_ROW + 1)
            if value is None or value == "":
                continue
            ws.cell(row=r, column=idx, value=value)

    # ---------- Дополнительные листы (точные колонки и порядок Ozon) ----------
    _build_extra_sheet(wb, "Озон.Видео", "Озон.Видео", [
        ("Артикул", True, ""),
        ("Озон.Видео: название", False, "Укажите название для видео."),
        ("Озон.Видео: ссылка", False,
         "Укажите ссылку на видео (MP4, MOV). Продолжительность от 8 сек до 5 минут, "
         "размер файла не более 2ГБ."),
        ("Озон.Видео: товары на видео", False,
         "Укажите товары, которые демонстрируются в вашем видео. Перечислите SKU через запятую (не более 5)."),
    ])
    _build_extra_sheet(wb, "Озон.Видеообложка", "Озон.Видеообложка", [
        ("Артикул", True, ""),
        ("Озон.Видеообложка: ссылка", False,
         "Укажите ссылку на видео (MP4, MOV). Продолжительность от 8 до 30 секунд, "
         "размер файла не более 20МБ."),
    ])
    _build_extra_sheet(wb, "Документация PDF", "Документация PDF", [
        ("Артикул", True, ""),
        ("Название файла PDF", False, ""),
        ("Документ PDF", False, "Прямая ссылка на PDF-файл: он должен открываться и скачиваться по ссылке."),
    ])

    return wb


def _build_extra_sheet(wb: Workbook, title: str, group_name: str, cols: list):
    """Доп. лист Ozon: строка 1 — блок, строка 2 — названия (+*), строка 3 — маркеры, строка 4 — подсказки."""
    ws = wb.create_sheet(title)
    for idx, (name, required, hint) in enumerate(cols, start=1):
        ws.cell(row=1, column=idx, value=group_name if idx > 1 else None)
        c2 = ws.cell(row=2, column=idx, value=name + ("*" if required else ""))
        c2.font = HEADER_FONT
        if required:
            c2.fill = RED_FILL
        ws.cell(row=3, column=idx, value="Обязательное поле" if required else None)
        ws.cell(row=4, column=idx, value=hint or None)
    return ws


# ========== Сборка книг Yandex / WB (базовая версия) ==========

def build_simple_workbook(platform: str, products: list, spec: Optional[dict]) -> Workbook:
    # ✅ Уникализация артикулов и для Yandex/WB
    _unique_articles(products)

    wb = Workbook()
    ws = wb.active
    ws.title = "Список товаров" if platform == "yandex" else "Товары"

    attributes = (spec or {}).get("attributes") or []
    columns = [
        {"header": "Артикул", "key": "article", "required": True, "type": "text", "values": None, "multi": False},
        {"header": "Название", "key": "name", "required": True, "type": "text", "values": None, "multi": False},
        {"header": "Цена", "key": "price", "required": True, "type": "number", "values": None, "multi": False},
        {"header": "Категория", "key": "category", "required": False, "type": "text", "values": None, "multi": False},
        {"header": "Штрихкод", "key": "barcode", "required": False, "type": "text", "values": None, "multi": True},
    ]
    for a in attributes:
        columns.append({
            "header": a["name"],
            "key": f"attr:{a['name']}",
            "required": bool(a.get("required")),
            "type": a.get("type", "text"),
            "values": a.get("values"),
            "multi": a.get("type") == "multiselect",
        })

    used_dicts = {}
    for idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=idx, value=col["header"] + ("*" if col["required"] else ""))
        cell.font = HEADER_FONT
        if col["required"]:
            cell.fill = RED_FILL
        if col["values"]:
            rng = f"{get_column_letter(idx)}2:{get_column_letter(idx)}{len(products) + 51}"
            if len(col["values"]) <= 8:
                dv = DataValidation(type="list",
                                    formula1='"' + ",".join(str(v) for v in col["values"]) + '"',
                                    allow_blank=True)
                ws.add_data_validation(dv)
                dv.add(rng)
            else:
                title = _add_dict_sheet(wb, col["header"], used_dicts)
                n = _fill_dict_sheet(wb, title, col["values"])
                dv = DataValidation(type="list", formula1=f"'{title}'!$A$1:$A${n}", allow_blank=True)
                ws.add_data_validation(dv)
                dv.add(rng)

    for r, product in enumerate(products, start=2):
        for idx, col in enumerate(columns, start=1):
            value = _ozon_cell_value(product, col, row_num=r - 1)
            if value is None or value == "":
                continue
            ws.cell(row=r, column=idx, value=value)

    if platform == "yandex":
        instr = wb.create_sheet("Инструкция")
        rules = [
            "Не меняйте структуру файла: не перемещайте столбцы и не переименовывайте листы.",
            "Красным выделены обязательные поля.",
            "Числа указывайте без единиц измерения.",
            "Несколько значений — через точку с запятой без пробелов.",
            "Не используйте табуляцию и переносы строк внутри ячеек.",
        ]
        for i, rule in enumerate(rules, start=1):
            instr.cell(row=i, column=1, value=rule)

    return wb


# ========== Оркестратор: группировка по категориям + zip ==========

def generate_export(products: list, specs_by_category: dict, platform: str):
    """
    Возвращает (bytes, filename).
    Одна категория → xlsx. Несколько → zip из xlsx (Ozon принимает шаблон на одну категорию).
    """
    groups = {}
    for p in products:
        cat = p.get("mapped_category") or p.get("category") or "Без категории"
        groups.setdefault(cat, []).append(p)

    files = []
    for cat, prods in groups.items():
        spec = specs_by_category.get(cat)
        if platform == "ozon":
            wb = build_ozon_workbook(prods, spec)
        else:
            wb = build_simple_workbook(platform, prods, spec)
        buf = io.BytesIO()
        wb.save(buf)
        files.append((f"{platform}_{_slug(cat)}", buf.getvalue()))

    if len(files) == 1:
        return files[0][1], f"{files[0][0]}.xlsx"

    zipbuf = io.BytesIO()
    with zipfile.ZipFile(zipbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(f"{name}.xlsx", data)
    return zipbuf.getvalue(), f"{platform}_export_{len(files)}_categories.zip"