"""
Генератор XLSX v2: файлы, СТРУКТУРНО идентичные реальным шаблонам Ozon и Яндекс Маркета.

✅ v9 (приоритет эталонных шаблонов для ВСЕХ площадок):
  - Если для площадки (Яндекс Маркет, Ozon, Wildberries, Магнит) загружен эталонный
    шаблон в разделе «Шаблоны», выгрузка собирается напрямую в оригинальном файле
    площадки через fill_official_template (удаляется строка-пример и дописываются товары).
  - Если эталон ещё не загружен — используется резервная генерация книги по структуре площадки.
"""

import io
import re
import zipfile

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
GRAY_FILL = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
YM_HINT_FILL = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
HEADER_FONT = Font(name="Arial", size=10, bold=True)
RED_HEADER_FONT = Font(name="Arial", size=10, bold=True, color="C00000")
GROUP_FONT = Font(name="Arial", size=13, bold=True, color="333333")
HINT_FONT = Font(name="Arial", size=8, color="333333")
DATA_FONT = Font(name="Arial", size=10)

THIN_SIDE = Side(style="thin", color="808080")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

DICT_LIMIT = 5000
DATA_START_ROW = 5

VAT_LABELS = {"none": "Не облагается", "22": "22", "10": "10", "7": "7", "5": "5"}

G_NAME = "Название"
G_PRICE = (
    "Цены\nЗаполняйте только при создании нового товара. Изменить цену существующего товара "
    "можно в разделе «Цены и акции → Обновить цены»"
)
G_PROMO = "Платное продвижение\nСамые популярные способы поднять конверсию"
G_SKU = (
    "Информация о товаре\nБлок можно не заполнять, если товар продается на Ozon "
    "и вы заполнили поле SKU"
)
G_EXTRA = (
    "Дополнительная информация о товаре\nБлок можно не заполнять, если товар продается на Ozon "
    'и вы заполнили либо поле SKU, либо блок "Информация о товаре"'
)
G_UNION = (
    "Одинаковые характеристики\nДля всех вариантов товара, которые вы хотите объединить "
    "на одной карточке, укажите одинаковые значения в этих полях"
)
G_VARIANT = (
    "Характеристики вариантов\nВы можете заполнить эти поля как одинаковыми значениями "
    "(если в этой характеристике вариант не отличается от других) или разными (если отличается)"
)
G_ATTRS = (
    "Характеристики\nБлок можно не заполнять, если товар продается на Ozon и вы заполнили "
    'либо поле SKU, либо блок "Информация о товаре"'
)

BRAND_NAMES = {"бренд", "бренд в одежде и обуви", "брендодеждыиобуви"}
RECOMMENDED_ONLY = {"российский размер", "пол"}

HINT_MAIN_PHOTO = (
    "Вы можете загрузить товары в xls-шаблоне и API без фото, а потом загрузить фото через карточку товара "
    "или раздел «Обновить изображения»\n\nТребования к изображениям\n\n- формат: jpeg, jpg, png;\n"
    "- разрешение: от 200px на 200px до 4320px на 7680px;\n- размер: не превышает 10МБ."
)

HINT_EXTRA_PHOTOS = (
    "Если загружаете дополнительные фотографии по отдельности, поочерёдно прикрепите ссылки "
    "для каждого изображения. Ограничение по количеству – 14 штук. Разделите ссылки пробелом."
)

OZON_BASE_COLUMNS = [
    ("№", "_row_num", False, "number", "", ""),
    (
        "Артикул",
        "article",
        True,
        "text",
        "Введите артикул товара или его номер в вашей базе. Артикул должен быть уникальным в рамках вашего ассортимента.",
        "",
    ),
    (
        "Название товара",
        "name",
        False,
        "text",
        "Ознакомьтесь с Требованиями к названию, чтобы указать правильное название товара и пройти модерацию.",
        G_NAME,
    ),
    (
        "Предельная цена без акций, руб.",
        "price",
        True,
        "number",
        "Цена, которую вы устанавливаете вручную.",
        G_PRICE,
    ),
    (
        "Зачёркнутая цена, руб.",
        "strike_price",
        False,
        "number",
        "Цена, которую покупатель видит зачёркнутой.",
        G_PRICE,
    ),
    (
        "НДС, %",
        "vat_rate",
        True,
        "select",
        "Укажите ставку НДС. Если товар не облагается НДС, или вы не платите НДС – укажите Не облагается.",
        G_PRICE,
    ),
    (
        "Рассрочка",
        "installment",
        False,
        "select",
        "Добавим товару пометку «Рассрочка 0–0–6».",
        G_PROMO,
    ),
    (
        "Ускоренный сбор отзывов",
        "reviews_boost",
        False,
        "select",
        "Подключим товару ускоренный сбор отзывов.",
        G_PROMO,
    ),
    (
        "SKU",
        "sku_copy",
        False,
        "text",
        "Заполните поле, если хотите скопировать чужой товар, размещённый на Ozon.",
        G_SKU,
    ),
    (
        "Штрихкод (Серийный номер / EAN)",
        "barcode",
        False,
        "text",
        "Введите штрихкод товара от производителя и наклейте его на упаковку.",
        G_SKU,
    ),
    (
        "ТН ВЭД коды ЕАЭС",
        "okpd_code",
        True,
        "select",
        "Выберите одно значение из списка.",
        G_EXTRA,
    ),
    (
        "Вес в упаковке, г",
        "package_weight_grams",
        True,
        "number",
        "Укажите вес единицы товара в граммах вместе с упаковкой. Введите только число.",
        G_EXTRA,
    ),
    (
        "Ширина упаковки, мм",
        "package_width_mm",
        True,
        "number",
        "Измерьте в миллиметрах ширину товара в упаковке.",
        G_EXTRA,
    ),
    (
        "Высота упаковки, мм",
        "package_height_mm",
        True,
        "number",
        "Измерьте в миллиметрах высоту товара в упаковке.",
        G_EXTRA,
    ),
    (
        "Длина упаковки, мм",
        "package_length_mm",
        True,
        "number",
        "Измерьте в миллиметрах длину товара в упаковке.",
        G_EXTRA,
    ),
    ("Ссылка на главное фото", "main_photo", True, "text", HINT_MAIN_PHOTO, G_EXTRA),
    ("Ссылки на дополнительные фото", "extra_photos", False, "text", HINT_EXTRA_PHOTOS, G_EXTRA),
    (
        "Артикул фото",
        "photo_article",
        False,
        "text",
        'Название файла с изображением товара.\nЗапрещенные символы: "/" и "_".',
        G_EXTRA,
    ),
]

# ==================== 48 колонок официального шаблона Яндекс Маркета ====================
YANDEX_TEMPLATE_COLUMNS = [
    (
        "Критичные ошибки",
        None,
        False,
        True,
        "",
        "Значение поля выгружено для информации. Не будет изменено при загрузке.\n\nСписок критичных ошибок по товару",
    ),
    (
        "Некритичные ошибки",
        None,
        False,
        True,
        "",
        "Значение поля выгружено для информации. Не будет изменено при загрузке.\n\nСписок некритичных ошибок по товару",
    ),
    (
        "Качество карточки",
        None,
        False,
        True,
        "",
        "Заполняется автоматически. Показывает, насколько хорошо заполнена карточка, и влияет на место в поиске. Чем выше товар в поиске, тем больше у него показов и заказов. Значение измеряется в баллах.",
    ),
    (
        "Ваш SKU *",
        "article",
        True,
        False,
        "Основные параметры",
        "Уникальный идентификатор товара, для которого будет передана цена",
    ),
    (
        "Название товара *",
        "name",
        True,
        False,
        "",
        "По схеме: тип товара + бренд или производитель + модель + отличительные характеристики",
    ),
    (
        "Ссылка на изображение *",
        "photos_comma",
        True,
        False,
        "",
        "Ссылка на изображение товара. Можно указать до 30 ссылок через запятую. Изображение по первой ссылке будет основным.",
    ),
    (
        "Описание товара *",
        "description",
        True,
        False,
        "",
        "Не более 6000 символов (включая знаки препинания)",
    ),
    (
        "Категория на Маркете *",
        "category",
        True,
        False,
        "",
        "Она помогает точнее определить категорию в каталоге Маркета.",
    ),
    (
        "Бренд *",
        "brand",
        True,
        False,
        "",
        "Название торговой марки, бренд или производитель товара.",
    ),
    (
        "Штрихкод *",
        "barcode_comma",
        True,
        False,
        "",
        "Если штрихкодов несколько, перечислите через запятую",
    ),
    (
        "Теги",
        "tags",
        False,
        False,
        "",
        "Можно указать до 10 тегов через запятую. Каждый тег — не более 20 знаков с пробелами.",
    ),
    (
        "Ссылка на видео",
        "video_url",
        False,
        False,
        "",
        "Это должны быть прямые ссылки на видео (ссылки, заканчивающиеся на MP4, WebM, MOV, QT, FLV, AVI). Размер — до 100 МБ, длительность - от 1 секунды до 20 минут.",
    ),
    (
        "Инструкции",
        "manuals",
        False,
        False,
        "",
        "Это должна быть прямая ссылка на инструкцию (ссылки, заканчивающиеся на PDF, JPG, PNG). Размер — до 30 МБ, можно указать до 6 ссылок через запятую.",
    ),
    (
        "Страна производства",
        "country",
        False,
        False,
        "",
        "Название на русском языке.",
    ),
    (
        "Артикул производителя",
        "vendor_code",
        False,
        False,
        "",
        "Код товара, который ему присваивает производитель. Если кодов несколько, укажите их через запятую.",
    ),
    (
        "Вес, кг *",
        "weight_kg",
        True,
        False,
        "Вес и габариты с упаковкой",
        "Вес товара в транспортной упаковке, можно с точностью до тысячных. Например, 1.528.",
    ),
    (
        "Длина, см *",
        "length_cm",
        True,
        False,
        "",
        "Длина упаковки, в которой передадите товар в доставку. Можно указать с точностью до тысячных — например, 65.55.",
    ),
    (
        "Ширина, см *",
        "width_cm",
        True,
        False,
        "",
        "Ширина упаковки, в которой передадите товар в доставку. Можно указать с точностью до тысячных — например, 65.55.",
    ),
    (
        "Высота, см *",
        "height_cm",
        True,
        False,
        "",
        "Высота упаковки, в которой передадите товар в доставку. Можно указать с точностью до тысячных — например, 65.55.",
    ),
    (
        "Товар доставляется в нескольких упаковках",
        "units_per_item",
        False,
        False,
        "",
        "Нет — оставьте поле пустым. Да — укажите количество грузовых мест.",
    ),
    (
        "Объём, л",
        None,
        False,
        True,
        "",
        "Заполняется автоматически. Рассчитываем как произведение длины, ширины и высоты в сантиметрах, поделённое на 1000.",
    ),
    (
        "Цена *",
        "price",
        True,
        False,
        "Цена",
        "Цена в валюте кабинета, по которой вы хотите продавать товар.",
    ),
    (
        "Зачёркнутая цена",
        "strike_price",
        False,
        False,
        "",
        "Цена до скидки в валюте кабинета, которую покупатели видят на витрине.",
    ),
    (
        "Себестоимость",
        None,
        False,
        False,
        "",
        "Стоимость затрат на самостоятельное производство товара или закупку у производителя или поставщиков.",
    ),
    (
        "Дополнительные расходы",
        None,
        False,
        False,
        "",
        "Дополнительные расходы на товар. Например, на доставку или упаковку.",
    ),
    (
        "Срок годности",
        "shelf_life",
        False,
        False,
        "Срок годности и службы",
        "В годах, месяцах, днях, неделях или часах",
    ),
    (
        "Комментарий к сроку годности",
        None,
        False,
        False,
        "",
        "Дополнительные условия хранения",
    ),
    (
        "Срок службы",
        "service_life",
        False,
        False,
        "",
        "В годах, месяцах, днях, неделях или часах",
    ),
    (
        "Комментарий к сроку службы",
        None,
        False,
        False,
        "",
        "Дополнительные условия использования",
    ),
    (
        "Гарантийный срок",
        "warranty",
        False,
        False,
        "Гарантийный срок",
        "В годах, месяцах, днях, неделях или часах",
    ),
    (
        "Комментарий к гарантийному сроку",
        None,
        False,
        False,
        "",
        "Дополнительные условия гарантии",
    ),
    (
        "Маркировка",
        "marking",
        False,
        False,
        "Маркировка и документы",
        "Выберите «Да», если товар маркируется в системе «Честный знак» — тогда при поставке или сборке заказа запросим КИЗ.",
    ),
    (
        "ТН ВЭД *",
        "okpd_code",
        True,
        False,
        "",
        "Код товарной номенклатуры внешнеэкономической деятельности ЕАЭС",
    ),
    (
        "ОКПД 2",
        "okpd2",
        False,
        False,
        "",
        "Код товара в Общероссийском классификаторе продукции по видам экономической деятельности",
    ),
    (
        "Номер документа на товар",
        "certificate",
        False,
        False,
        "",
        "Например, сертификата или декларации соответствия. Если документов несколько, перечислите через запятую",
    ),
    (
        "Тип уценки",
        None,
        False,
        False,
        "Уценка",
        "Заполните, если ваш товар уже был в употреблении или имеет незначительные дефекты.",
    ),
    (
        "Внешний вид товара",
        None,
        False,
        False,
        "",
        "Выберите значение из списка: как новый, отличный, хороший.",
    ),
    (
        "Описание состояния товара",
        None,
        False,
        False,
        "",
        "Короткое описание следов использования или дефектов товара.",
    ),
    (
        "Особый тип товара",
        None,
        False,
        False,
        "Дополнительно",
        "Выберите значение из списка, чтобы товар попал в правильную категорию и на нужную карточку.",
    ),
    (
        "С какого возраста пользоваться",
        "age_limit",
        False,
        False,
        "",
        "Если товаром можно пользоваться только с определенного возраста, укажите его.",
    ),
    (
        "Товар для взрослых",
        "adult",
        False,
        False,
        "",
        "Укажите, если товар относится к удовлетворению сексуальных потребностей. Если нет, оставьте поле пустым.",
    ),
    (
        "Цифровой товар",
        None,
        False,
        False,
        "",
        "Параметр устанавливается для цифровых товаров, которые просто скачиваются. Если нет — оставьте поле пустым.",
    ),
    (
        "Характеристики товара",
        "ym_characteristics",
        False,
        False,
        "",
        "Все важные характеристики товара — цвет, размер, объем, материал, возраст, пол, и т. д.",
    ),
    (
        "В архиве",
        "archived",
        False,
        False,
        "",
        "Помещен ли товар в архив каталога. При перемещении товара в архив, он скрывается с витрины для всех магазинов кабинета.",
    ),
    (
        "Артикул товара (SKU)",
        None,
        False,
        False,
        "",
        "Если вы знаете SKU на Маркете, заполните это поле. В противном случае оставьте его пустым",
    ),
    (
        "Артикул Маркета",
        None,
        False,
        True,
        "",
        "Значение поля выгружено для информации. Не будет изменено при загрузке.",
    ),
    (
        "Категория на Маркете",
        None,
        False,
        True,
        "",
        "Значение поля выгружено для информации. Не будет изменено при загрузке.\n\nТекущая категория товара в каталоге Маркета",
    ),
    (
        "Дата дополнения карточки",
        None,
        False,
        True,
        "",
        "Не удаляйте и не меняйте данный столбец - он заполняется автоматически.\nПоказывает, когда на карточке менялись данные, которые дополнил Маркет.",
    ),
]

YANDEX_GROUP_MERGES = [
    (1, 3),
    (4, 15),
    (16, 21),
    (22, 25),
    (26, 29),
    (30, 31),
    (32, 35),
    (36, 38),
    (39, 45),
    (46, 48),
]


# ========== Вспомогательные функции ==========


def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Zа-яА-Я]+", "_", name).strip("_")[:40] or "category"


def _norm(name: str) -> str:
    return re.sub(r"[^a-zа-я0-9]", "", (name or "").lower())


def _strip_html(text: str) -> str:
    """Очищает описание товара от HTML-тегов (<p>, <br>, <div> и сущностей)."""
    if not text:
        return ""
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", str(text))
    cleaned = re.sub(r"(?i)</p>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">")):
        cleaned = cleaned.replace(ent, ch)
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def _guess_yandex_category(product: dict) -> str:
    """
    Возвращает валидное название категории для Яндекс Маркета.
    Исключает невалидное системное значение «Не указана» / «Без категории».
    """
    for field in ("mapped_category", "category"):
        raw = (product.get(field) or "").strip()
        if raw and raw.lower() not in ("не указана", "без категории", "не маппировалось", "—"):
            parts = [p.strip() for p in re.split(r"[/\\>]", raw) if p.strip()]
            return parts[-1] if parts else raw

    name_low = (product.get("name") or "").lower()
    rules = [
        (["футболк", "майк", "лонгслив"], "Футболки и майки"),
        (["плать", "сарафан"], "Платья и сарафаны"),
        (["брюк", "джинс", "штаны", "леггинс"], "Брюки"),
        (["куртк", "пуховик", "ветровк", "пальто"], "Верхняя одежда"),
        (["толстовк", "худи", "свитшот", "джемпер", "свитер"], "Толстовки, свитшоты и худи"),
        (["носки", "гольф", "колготк"], "Носки, чулки и колготки"),
        (["кроссовк", "кеды"], "Кроссовки и кеды"),
        (["ботинк", "сапог", "туфл"], "Обувь"),
        (["смартфон", "телефон"], "Мобильные телефоны"),
        (["наушник", "гарнитур"], "Наушники и Bluetooth-гарнитуры"),
        (["швабр", "ведро", "щетк"], "Инвентарь для уборки"),
        (["кружк", "чашк", "стакан", "миск", "салатник", "тарелк"], "Столовая посуда"),
        (["лампа", "светильник", "люстр"], "Освещение"),
        (["чай"], "Чай"),
        (["кофе"], "Кофе"),
        (["книг"], "Книги"),
        (["игрушк", "конструктор", "кукл"], "Игрушки"),
    ]
    for keywords, ym_cat in rules:
        if any(k in name_low for k in keywords):
            return ym_cat
    return "Товары для дома"


def _match_enum_case(value: str, values: list) -> str:
    low = (value or "").strip().lower()
    for v in values or []:
        if str(v).strip().lower() == low:
            return str(v)
    return (value or "").strip()


def _normalize_multi(value: str) -> str:
    parts = re.split(r"[;,]", value or "")
    return ";".join(p.strip() for p in parts if p.strip())


def _generate_ean13(product: dict) -> str:
    """
    Генерирует валидный 13-значный штрихкод EAN-13 (префикс 200 + ID товара + контрольная цифра GS1),
    если у товара не указан собственный штрихкод (обязательно для Яндекс Маркета и WB).
    """
    pid = int(product.get("id") or 1)
    base12 = f"200{pid:09d}"[:12]
    odd_sum = sum(int(base12[i]) for i in range(0, 12, 2))
    even_sum = sum(int(base12[i]) for i in range(1, 12, 2))
    check_digit = (10 - ((odd_sum + even_sum * 3) % 10)) % 10
    return f"{base12}{check_digit}"


def _add_dict_sheet(wb: Workbook, attr_name: str, used: dict) -> str:
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


def _is_brand_name(name: str) -> bool:
    return _norm(name) in {_norm(b) for b in BRAND_NAMES}


def _attr_group(attr: dict) -> str:
    name = attr.get("name") or ""
    if _is_brand_name(name) or "объедин" in name.lower():
        return G_UNION
    if (attr.get("group") or "") == "variant":
        return G_VARIANT
    return G_ATTRS


def _row3_marker(col: dict) -> str | None:
    parts = []
    if col["required"]:
        parts.append("Обязательное поле")
    elif col.get("recommended"):
        parts.append("Рекомендуем к заполнению")
    if col.get("is_brand"):
        parts.append("ϟ  Влияет на продвижение")
    if col["multi"]:
        if col.get("max_count"):
            parts.append(f"Ⓜ️ Не более {col['max_count']} вариантов")
        else:
            parts.append("Ⓜ️ Множественный выбор")
    return "\n".join(parts) if parts else None


def _unique_articles(products: list) -> None:
    seen = {}
    for p in products:
        base = p.get("sku") or p.get("external_id") or f"ID{p.get('id')}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        p["_article"] = base if count == 1 else f"{base}_{count}"


# ========== Значения ячеек Ozon ==========


def _cell_value(product: dict, col: dict, attr_map: dict, row_num: int):
    key = col["key"]
    if key is None:
        return None
    if key == "_row_num":
        return row_num
    if key == "article":
        return (
            product.get("_article")
            or product.get("sku")
            or product.get("external_id")
            or f"ID{product.get('id')}"
        )
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
    if key in (
        "package_weight_grams",
        "package_width_mm",
        "package_height_mm",
        "package_length_mm",
    ):
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
        norm_key = key[5:]
        raw = attr_map.get(norm_key)
        if raw in (None, "") and norm_key in ("brand", "model"):
            for syn in (
                ["бренд", "брендводеждеиобуви"]
                if norm_key == "brand"
                else [
                    "названиемодели",
                    "названиемоделидляобъединенияводнукарточку",
                    "объединитьнаоднойкарточке",
                    "модель",
                ]
            ):
                if syn in attr_map and attr_map[syn] not in (None, ""):
                    raw = attr_map[syn]
                    break
        if raw in (None, "") and norm_key == "model":
            raw = product.get("name")
        if raw in (None, "") and norm_key == "marking":
            raw = "Нет"
        if norm_key in ("количествовупаковке", "количествовупаковкешт") and raw in (None, ""):
            raw = product.get("units_per_item") or 1
        if raw in (None, ""):
            return None
        if col["multi"]:
            return _normalize_multi(str(raw))
        if col.get("values"):
            return _match_enum_case(str(raw), col["values"])
        if col["type"] == "number":
            try:
                v = float(raw)
                return int(v) if v == int(v) else v
            except (TypeError, ValueError):
                return raw
        return str(raw)
    return None


# ========== Сборка резервной книги Яндекс Маркета ==========


def _yandex_cell_value(product: dict, key: str | None, attr_map: dict):
    if not key:
        return None
    if key == "article":
        return (
            product.get("_article")
            or product.get("sku")
            or product.get("external_id")
            or f"YM-{product.get('id')}"
        )
    if key == "name":
        return product.get("name")
    if key == "photos_comma":
        photos = product.get("photos") or []
        return ", ".join(str(u) for u in photos[:30]) if photos else None
    if key == "description":
        raw_desc = product.get("description") or product.get("name") or ""
        clean_desc = _strip_html(raw_desc)
        return clean_desc[:6000] if clean_desc else product.get("name")
    if key == "category":
        return _guess_yandex_category(product)
    if key == "brand":
        raw_brand = (
            product.get("brand")
            or attr_map.get("бренд")
            or attr_map.get("брендводеждеиобуви")
            or ""
        ).strip()
        if not raw_brand or raw_brand.lower() in (
            "отсутствует бренд",
            "без бренда",
            "noname",
            "no name",
            "нет",
        ):
            return "Нет бренда"
        return raw_brand
    if key == "barcode_comma":
        bc = product.get("barcode") or attr_map.get("штрихкод") or ""
        parts = [p.strip() for p in re.split(r"[;,]", str(bc)) if p.strip()]
        if parts:
            return ", ".join(parts)
        for v in product.get("variants") or []:
            v_sku = str(v.get("sku") or "").strip()
            if v_sku.isdigit() and 8 <= len(v_sku) <= 14:
                return v_sku
        return _generate_ean13(product)
    if key == "country":
        return attr_map.get("странапроизводства") or attr_map.get("странаизготовитель") or "Россия"
    if key == "vendor_code":
        return product.get("sku") or product.get("_article")
    if key == "weight_kg":
        wg = product.get("package_weight_grams") or product.get("weight_grams")
        return round(float(wg) / 1000.0, 3) if wg else None
    if key == "length_cm":
        mm = product.get("package_length_mm")
        return round(float(mm) / 10.0, 2) if mm else None
    if key == "width_cm":
        mm = product.get("package_width_mm")
        return round(float(mm) / 10.0, 2) if mm else None
    if key == "height_cm":
        mm = product.get("package_height_mm")
        return round(float(mm) / 10.0, 2) if mm else None
    if key == "units_per_item":
        u = product.get("units_per_item")
        return int(u) if u and int(u) > 1 else None
    if key == "price":
        return product.get("price")
    if key == "strike_price":
        return product.get("strike_price")
    if key == "marking":
        m = attr_map.get("нуженкодмаркировки") or attr_map.get("маркировка")
        if m and str(m).strip().lower() == "да":
            return "Да"
        return None
    if key == "okpd_code":
        return product.get("okpd_code") or attr_map.get("тнвэдкодыеаэс") or attr_map.get("тнвэд")
    if key == "archived":
        return "Нет"
    if key == "ym_characteristics":
        skip_norms = {
            "бренд",
            "брендводеждеиобуви",
            "странапроизводства",
            "странаизготовитель",
            "нуженкодмаркировки",
            "маркировка",
            "тнвэдкодыеаэс",
            "тнвэд",
            "названиемодели",
            "названиемоделидляобъединенияводнукарточку",
            "объединитьнаоднойкарточке",
            "модель",
            "тип",
        }
        pairs = []
        for a in product.get("attributes") or []:
            aname = (a.get("name") or "").strip()
            aval = (a.get("value") or "").strip()
            if not aname or not aval or _norm(aname) in skip_norms:
                continue
            pairs.append(f"{aname}|{aval}")
        return ";".join(pairs) if pairs else None
    return None


def _populate_yandex_instruction_sheet(ws) -> None:
    """Заполняет 1-й лист «Инструкция» точно по образцу Яндекс Маркета."""
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 85

    title_font = Font(name="Arial", size=16, bold=True)
    step_font = Font(name="Arial", size=13, bold=True)
    bold_font = Font(name="Arial", size=10, bold=True)
    text_font = Font(name="Arial", size=10)
    link_font = Font(name="Arial", size=10, color="0066CC", underline="single")
    step_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    wrap = Alignment(wrap_text=True, vertical="center")

    ws.merge_cells("A1:B1")
    ws["A1"] = "Инструкция"
    ws["A1"].font = title_font
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:B2")
    ws["A2"] = "Шаг 1. Заполните шаблон"
    ws["A2"].font = step_font
    ws["A2"].fill = step_fill
    ws["B2"].fill = step_fill
    ws.row_dimensions[2].height = 28

    step1_rows = [
        (
            "Перейдите на лист Список товаров, изучите пример заполненного товара, но не забудьте удалить "
            "его перед загрузкой каталога. Если этого не сделать, мы создадим такой товар в вашем каталоге.",
            text_font,
            34,
        ),
        (
            "Добавьте ваши товары. Обязательные для заполнения поля выделены красным цветом и помечены "
            "звездочкой (*). Без них товар не появится в каталоге или мы не сможем создать карточку для этого товара.",
            text_font,
            34,
        ),
        ("Наведите на название поля, чтобы узнать, как его правильно заполнить.", text_font, 22),
        ('Подробные рекомендации по заполнению полей см. на листе «Описание полей»', link_font, 22),
        ("Одна строка на листе Список товаров должна соответствовать одному вашему товару.", text_font, 22),
        (
            "На листе Список товаров нельзя: изменять названия полей, удалять столбцы, менять их местами.",
            text_font,
            22,
        ),
        ("В шаблоне нельзя: изменять названия листов, удалять листы, менять их местами.", text_font, 22),
    ]

    cur_row = 3
    for text, fnt, h in step1_rows:
        ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=2)
        cell = ws.cell(row=cur_row, column=1, value=text)
        cell.font = fnt
        cell.alignment = wrap
        ws.row_dimensions[cur_row].height = h
        cur_row += 1

    ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=2)
    ws.cell(row=cur_row, column=1, value="Шаг 2. Загрузите шаблон в систему").font = step_font
    ws.cell(row=cur_row, column=1).fill = step_fill
    ws.cell(row=cur_row, column=2).fill = step_fill
    ws.row_dimensions[cur_row].height = 28
    cur_row += 1

    for text in (
        "Перейдите в раздел Товары → Каталог.",
        "Выберите Загрузить товары и загрузите этот шаблон в появившемся окне.",
    ):
        ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=2)
        c = ws.cell(row=cur_row, column=1, value=text)
        c.font = text_font
        c.alignment = wrap
        ws.row_dimensions[cur_row].height = 24
        cur_row += 1

    ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=2)
    ws.cell(row=cur_row, column=1, value="Шаг 3. Дождитесь проверки ассортимента").font = step_font
    ws.cell(row=cur_row, column=1).fill = step_fill
    ws.cell(row=cur_row, column=2).fill = step_fill
    ws.row_dimensions[cur_row].height = 28
    cur_row += 1

    ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=2)
    c = ws.cell(
        row=cur_row,
        column=1,
        value=(
            "Проверка товаров длится от пары часов до нескольких дней. Её результаты вы увидите в разделе "
            "Каталог. У каждого товара появится:"
        ),
    )
    c.font = text_font
    c.alignment = wrap
    ws.row_dimensions[cur_row].height = 32
    cur_row += 1

    status_rows = [
        ("Статус карточки", "Для продажи на Маркете нужно, чтобы товар был привязан к карточке."),
        (
            "Статус товара",
            "Показывает, продается ли товар по выбранной модели или в нем есть ошибки, которые нужно исправить.",
        ),
        (
            "Ошибки",
            "Все ошибки вы можете посмотреть в личном кабинете на странице редактирования каждого товара.",
        ),
    ]
    for label, desc in status_rows:
        c1 = ws.cell(row=cur_row, column=1, value=label)
        c1.font = bold_font
        c1.alignment = wrap
        c2 = ws.cell(row=cur_row, column=2, value=desc)
        c2.font = text_font
        c2.alignment = wrap
        ws.row_dimensions[cur_row].height = 28
        cur_row += 1

    ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=2)
    c_link = ws.cell(row=cur_row, column=1, value="Подробнее о статусах можно узнать в Справке.")
    c_link.font = link_font
    c_link.alignment = wrap
    ws.row_dimensions[cur_row].height = 24


def build_yandex_workbook(products: list, spec: dict | None = None) -> Workbook:
    """
    Резервный генератор книги Яндекс Маркета с 2 листами («Инструкция» и «Список товаров»),
    используемый, если пользователь ещё не загрузил эталонный шаблон Яндекс Маркета.
    """
    _unique_articles(products)
    wb = Workbook()

    ws_instr = wb.active
    ws_instr.title = "Инструкция"
    _populate_yandex_instruction_sheet(ws_instr)

    ws = wb.create_sheet("Список товаров")
    wrap_align = Alignment(wrap_text=True, vertical="top")
    group_align = Alignment(horizontal="left", vertical="center")

    for col_idx, (header, key, required, is_gray, group_title, hint) in enumerate(
        YANDEX_TEMPLATE_COLUMNS, start=1
    ):
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = 24

        c1 = ws.cell(row=1, column=col_idx, value=group_title or None)
        c1.font = GROUP_FONT
        c1.alignment = group_align
        c1.border = CELL_BORDER

        c2 = ws.cell(row=2, column=col_idx, value=header)
        c2.font = RED_HEADER_FONT if required else HEADER_FONT
        c2.alignment = wrap_align
        c2.border = CELL_BORDER
        if is_gray:
            c1.fill = GRAY_FILL
            c2.fill = GRAY_FILL

        c3 = ws.cell(row=3, column=col_idx, value=hint or None)
        c3.font = HINT_FONT
        c3.alignment = wrap_align
        c3.fill = GRAY_FILL if is_gray else YM_HINT_FILL
        c3.border = CELL_BORDER

    for start_col, end_col in YANDEX_GROUP_MERGES:
        ws.merge_cells(start_row=1, start_column=start_col, end_row=1, end_column=end_col)

    ws.row_dimensions[1].height = 26
    ws.row_dimensions[2].height = 28
    ws.row_dimensions[3].height = 95

    ym_data_start = 4
    for i, product in enumerate(products):
        r = ym_data_start + i
        attr_map = {
            _norm(a.get("name")): a.get("value")
            for a in (product.get("attributes") or [])
            if a.get("name")
        }
        for col_idx, (_, key, _, is_gray, _, _) in enumerate(YANDEX_TEMPLATE_COLUMNS, start=1):
            cell = ws.cell(row=r, column=col_idx)
            cell.font = DATA_FONT
            if is_gray:
                cell.fill = GRAY_FILL
                continue
            val = _yandex_cell_value(product, key, attr_map)
            if val not in (None, ""):
                cell.value = val

    wb.active = ws
    return wb


# ========== Сборка книги Ozon ==========


def build_ozon_workbook(products: list, spec: dict | None) -> Workbook:
    """Шапка 1:1 с официальным шаблоном категории: база 18 колонок + атрибуты спека по порядку."""
    _unique_articles(products)

    wb = Workbook()
    ws = wb.active
    ws.title = "Шаблон"

    columns = []
    for header, key, required, ctype, hint, group in OZON_BASE_COLUMNS:
        columns.append(
            {
                "header": header,
                "key": key,
                "required": required,
                "type": ctype,
                "hint": hint,
                "group": group,
                "values": None,
                "multi": False,
                "max_count": None,
                "is_brand": False,
                "recommended": False,
            }
        )
    for col in columns:
        if col["key"] == "vat_rate":
            col["values"] = ["Не облагается", "22", "10", "7", "5"]
        elif col["key"] in ("installment", "reviews_boost"):
            col["values"] = ["Да", "Нет"]

    for a in (spec or {}).get("attributes") or []:
        name = a.get("name") or ""
        if not name:
            continue
        norm = _norm(name)
        recommended = norm in RECOMMENDED_ONLY
        required = bool(a.get("required")) and not recommended
        columns.append(
            {
                "header": name,
                "key": f"attr:{norm}",
                "required": required,
                "recommended": recommended,
                "type": a.get("type", "text"),
                "hint": a.get("description") or "",
                "group": _attr_group(a),
                "values": a.get("values"),
                "multi": a.get("type") == "multiselect",
                "max_count": a.get("max_count"),
                "is_brand": _is_brand_name(name),
            }
        )

    columns.append(
        {
            "header": "Ошибка",
            "key": None,
            "required": False,
            "recommended": False,
            "type": "text",
            "hint": "Критичная ошибка в характеристиках товара. Товар с ошибками не будет продаваться.",
            "group": "",
            "values": None,
            "multi": False,
            "max_count": None,
            "is_brand": False,
        }
    )
    columns.append(
        {
            "header": "Недочёты",
            "key": None,
            "required": False,
            "recommended": False,
            "type": "text",
            "hint": "Устаревшее или незаполненное значение в характеристиках товара.",
            "group": "",
            "values": None,
            "multi": False,
            "max_count": None,
            "is_brand": False,
        }
    )

    used_dicts = {}
    last_row = max(DATA_START_ROW + len(products) - 1, DATA_START_ROW) + 50

    for idx, col in enumerate(columns, start=1):
        letter = get_column_letter(idx)
        ws.cell(row=1, column=idx, value=col["group"] or None)

        c2 = ws.cell(row=2, column=idx, value=col["header"] + ("*" if col["required"] else ""))
        c2.font = HEADER_FONT
        if col["required"]:
            c2.fill = RED_FILL

        ws.cell(row=3, column=idx, value=_row3_marker(col))

        hint = col["hint"]
        if not hint and col["values"]:
            hint = "Выберите значение из списка. Примеры: " + "; ".join(
                str(v) for v in col["values"][:5]
            )
        ws.cell(row=4, column=idx, value=hint or None)

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
                dv = DataValidation(
                    type="list", formula1=f"'{title}'!$A$1:$A${n}", allow_blank=True
                )
                ws.add_data_validation(dv)
                dv.add(rng)

    for r, product in enumerate(products, start=DATA_START_ROW):
        attr_map = {
            _norm(a.get("name")): a.get("value")
            for a in (product.get("attributes") or [])
            if a.get("name")
        }
        for idx, col in enumerate(columns, start=1):
            value = _cell_value(product, col, attr_map, row_num=r - DATA_START_ROW + 1)
            if value is None or value == "":
                continue
            ws.cell(row=r, column=idx, value=value)

    _build_extra_sheet(
        wb,
        "Озон.Видео",
        "Озон.Видео",
        [
            ("Артикул", True, ""),
            ("Озон.Видео: название", False, "Укажите название для видео "),
            ("Озон.Видео: ссылка", False, "Укажите ссылку на видео (MP4, MOV)."),
            ("Озон.Видео: товары на видео", False, "Перечислите SKU через запятую (не более 5)."),
        ],
    )
    _build_extra_sheet(
        wb,
        "Озон.Видеообложка",
        "Озон.Видеообложка",
        [
            ("Артикул", True, ""),
            ("Озон.Видеообложка: ссылка", False, "Укажите ссылку на видео (MP4, MOV)."),
        ],
    )
    _build_extra_sheet(
        wb,
        "Документация PDF",
        "Документация PDF",
        [
            ("Артикул", True, ""),
            ("Название файла PDF", False, ""),
            ("Документ PDF", False, "Прямая ссылка на PDF-файл."),
        ],
    )

    return wb


def _build_extra_sheet(wb: Workbook, title: str, group_name: str, cols: list):
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


# ========== Сборка книг WB ==========


def build_simple_workbook(platform: str, products: list, spec: dict | None) -> Workbook:
    _unique_articles(products)
    wb = Workbook()
    ws = wb.active
    ws.title = "Товары"

    columns = [
        {"header": "Артикул", "key": "article", "required": True, "type": "text", "values": None, "multi": False},
        {"header": "Название", "key": "name", "required": True, "type": "text", "values": None, "multi": False},
        {"header": "Цена", "key": "price", "required": True, "type": "number", "values": None, "multi": False},
        {"header": "Категория", "key": "category", "required": False, "type": "text", "values": None, "multi": False},
        {"header": "Штрихкод", "key": "barcode", "required": False, "type": "text", "values": None, "multi": True},
    ]
    for a in (spec or {}).get("attributes") or []:
        columns.append(
            {
                "header": a["name"],
                "key": f"attr:{_norm(a['name'])}",
                "required": bool(a.get("required")),
                "type": a.get("type", "text"),
                "values": a.get("values"),
                "multi": a.get("type") == "multiselect",
            }
        )

    used_dicts = {}
    for idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=idx, value=col["header"] + ("*" if col["required"] else ""))
        cell.font = HEADER_FONT
        if col["required"]:
            cell.fill = RED_FILL
        if col["values"]:
            rng = f"{get_column_letter(idx)}2:{get_column_letter(idx)}{len(products) + 51}"
            if len(col["values"]) <= 8:
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
                dv = DataValidation(
                    type="list", formula1=f"'{title}'!$A$1:$A${n}", allow_blank=True
                )
                ws.add_data_validation(dv)
                dv.add(rng)

    for r, product in enumerate(products, start=2):
        attr_map = {
            _norm(a.get("name")): a.get("value")
            for a in (product.get("attributes") or [])
            if a.get("name")
        }
        for idx, col in enumerate(columns, start=1):
            value = _cell_value(product, col, attr_map, row_num=r - 1)
            if value is None or value == "":
                continue
            ws.cell(row=r, column=idx, value=value)

    return wb


# ========== Оркестратор ==========


def generate_export(products: list, specs_by_category: dict, platform: str):
    """
    Возвращает (bytes, filename).
    ✅ Приоритет 1: эталонный шаблон площадки (Яндекс Маркет, Ozon, WB, Магнит),
       загруженный в разделе «Шаблоны» — открывается как каркас, зачищается пример
       и заполняется товарами (формат 1:1 с кабинетом площадки).
    ✅ Приоритет 2 (если эталон не загружен): генерация книги по структуре площадки.
    """
    from services.template_filler import fill_official_template, has_official_template

    # Яндекс Маркет принимает все товары разных категорий на одном листе «Список товаров»
    if platform == "yandex":
        first_cat = (
            (products[0].get("mapped_category") or products[0].get("category") or "")
            if products
            else ""
        )
        if has_official_template(first_cat, platform="yandex"):
            data = fill_official_template(first_cat, products, spec=None, platform="yandex")
            return data, "yandex_market_assortment.xlsx"

        wb = build_yandex_workbook(products)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), "yandex_market_assortment.xlsx"

    groups = {}
    for p in products:
        cat = p.get("mapped_category") or p.get("category") or "Без категории"
        groups.setdefault(cat, []).append(p)

    files = []
    for cat, prods in groups.items():
        if has_official_template(cat, platform=platform):
            files.append(
                (
                    f"{platform}_{_slug(cat)}",
                    fill_official_template(
                        cat, prods, specs_by_category.get(cat), platform=platform
                    ),
                )
            )
            continue
        spec = specs_by_category.get(cat)
        wb = (
            build_ozon_workbook(prods, spec)
            if platform == "ozon"
            else build_simple_workbook(platform, prods, spec)
        )
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