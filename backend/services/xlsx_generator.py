"""
Генератор XLSX v2: файлы, СТРУКТТУРНО идентичные реальным шаблонам Ozon.

✅ v4 — ШАПКА СТРОИТСЯ ИЗ СПЕКА КАТЕГОРИИ (platform_category_specs), а не из
фиксированного списка: порядок колонок, имена, звёздочки, маркеры строки 3
(«Обязательное поле», «Рекомендуем к заполнению», «Ⓜ️ Множественный выбор»,
«Ⓜ️ Не более N вариантов», «ϟ Влияет на продвижение»), подсказки строки 4
(description из спека) и группы строки 1 — как в официальном шаблоне категории.

Структура листа «Шаблон» (эталон 24–25.09.2026):
  строка 1 — группы-блоки;
  строка 2 — названия колонок, обязательные со звёздочкой;
  строка 3 — маркеры;
  строка 4 — подсказки;
  строка 5+ — данные товаров.
База: 18 фиксированных колонок (№ … Артикул фото) + атрибуты спека по порядку
+ служебные «Ошибка», «Недочёты». Листы: «Озон.Видео», «Озон.Видеообложка»,
«Документация PDF».
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
DATA_START_ROW = 5

VAT_LABELS = {"none": "Не облагается", "22": "22", "10": "10", "7": "7", "5": "5"}

# ==================== Группы-блоки строки 1 (дословно из эталонов) ====================
G_NAME = "Название"
G_PRICE = ("Цены\nЗаполняйте только при создании нового товара. Изменить цену существующего товара "
           "можно в разделе «Цены и акции → Обновить цены»")
G_PROMO = "Платное продвижение\nСамые популярные способы поднять конверсию"
G_SKU = ("Информация о товаре\nБлок можно не заполнять, если товар продается на Ozon "
         "и вы заполнили поле SKU")
G_EXTRA = ("Дополнительная информация о товаре\nБлок можно не заполнять, если товар продается на Ozon "
           'и вы заполнили либо поле SKU, либо блок "Информация о товаре"')
G_UNION = ("Одинаковые характеристики\nДля всех вариантов товара, которые вы хотите объединить "
           "на одной карточке, укажите одинаковые значения в этих полях")
G_VARIANT = ("Характеристики вариантов\nВы можете заполнить эти поля как одинаковыми значениями "
             "(если в этой характеристике вариант не отличается от других) или разными (если отличается)")
G_ATTRS = ("Характеристики\nБлок можно не заполнять, если товар продается на Ozon и вы заполнили "
           'либо поле SKU, либо блок "Информация о товаре"')

BRAND_NAMES = {"бренд", "бренд в одежде и обуви", "брендодеждыиобуви"}

# ✅ Эталонные исключения: в официальных шаблонах эти атрибуты помечены
# «Рекомендуем к заполнению» БЕЗ звёздочки, хотя в API-спеке is_required=true.
RECOMMENDED_ONLY = {"российский размер", "пол"}

HINT_MAIN_PHOTO = (
    "Вы можете загрузить товары в xls-шаблоне и API без фото, а потом загрузить фото через карточку товара "
    "или раздел «Обновить изображения»\n\nТребования к изображениям\n\n- формат: jpeg, jpg, png;\n"
    "- разрешение: от 200px на 200px до 4320px на 7680px;\n- размер: не привышает 10МБ;\n"
    "- фон: белый или светлый. Для белых или прозрачных товаров допустим черный фон. Для категории товаров "
    "Одежда, обувь и аксессуары фон серый (#f2f3f5);\nназвание: не может содержать символы «/» и «_».Нельзя использовать\n"
    "- изображения алкоголя;\n- эскизы товара (например, 3D-модели);\n- любые надписи (цены, логотипы, водяные знаки, контакты и пр);\n"
    "- чёрно-белые фото, фото с рамками и полосками;\n- размытые, нерезкие, некачественные фото;\n"
    "- фотографии сделанные в «домашних условиях»: на фоне ковра, мебели с тенями от других предметов.\n\n"
    "Требования к фото 18+\nНа изображениях должны быть размыты или скрыты другим образом интимные части тела.\n\n"
    "Если найдём в карточке запрещённую информацию, возьмём плату за обработку каждого нарушения.\n"
    "Подробнее https://seller-edu.ozon.ru/work-with-goods/zagruzka-tovarov/creating-goods/oshibki-pri-rabote-s-kartochkami\n\n"
    "Краткое требование к ссылкам\n\nДля загрузки главного фото можно добавить только одну ссылку, лишние ссылки не будут использованы.\n\n"
    "Прямая ссылка на изображение\n\nПо ссылкам должны открываться и скачиваться только сами изображения. Обычно такие ссылки заканчиваются "
    "символами: *.jpeg, *.jpg, *.png, но есть исключение – ссылки на Яндекс.Диск. Они доступны в формате "
    "https://yadi.sk/i/qUXcCwzmryWINw или https://disk.yandex.ru/i/qUXcCwzmryWINw\n\nПравильная ссылка:\n"
    "- не содержит дополнительных портов;\n- не ведет на HTML-страницу с изображением. Например, нельзя указывать ссылку на обзор товара, "
    "в котором есть фотографии;\n- не требует авторизации для доступа к изображению.\n\n"
    "Подробнее о требованиях можно узнать в https://seller-edu.ozon.ru/work-with-goods/trebovaniya-k-kartochkam-tovarov/media/foto-i-video-tovara"
)

HINT_EXTRA_PHOTOS = (
    "Вы можете загрузить товары в xls-шаблоне и API без фото, а потом загрузить фото через карточку товара "
    "или раздел «Обновить изображения»\n\nТребования к изображениям\n\n- формат: jpeg, jpg, png;\n"
    "- разрешение: от 200px на 200px до 4320px на 7680px;\n- размер: не превышает 10МБ;\n"
    "- фон: белый или светлый. Для белых или прозрачных товаров допустим черный фон. Для категории товаров "
    "Одежда, обувь и аксессуары фон серый (#f2f3f5).\n- название: не может содержать символ «/».Нельзя использовать\n"
    "- изображения алкоголя;\n- эскизы товара (например, 3D-модели);\n- любые надписи (цены, логотипы, водяные знаки, контакты и пр);\n"
    "- чёрно-белые фото, фото с рамками и полосками;\n- размытые, нерезкие, некачественные фото;\n"
    "- фотографии сделанные в «домашних условиях»: на фоне ковра, мебели с тенями от других предметов.\n\n"
    "Требования к фото 18+\nНа изображениях должны быть размыты или скрыты другим образом интимные части тела.\n\n"
    "Если найдём в карточке запрещённую информацию, возьмём плату за обработку каждого нарушения.\n"
    "Подробнее https://seller-edu.ozon.ru/work-with-goods/zagruzka-tovarov/creating-goods/oshibki-pri-rabote-s-kartochkami\n\n"
    "Краткое требование к ссылкам\n\nПрямая ссылка на изображение\nЕсли загружаете дополнительные фотографии по отдельности, поочерёдно "
    "прикрепите ссылки для каждого изображения. Ограничение по количеству – 14 штук. По ссылкам должны открываться и скачиваться только сами "
    "изображения. Обычно такие ссылки заканчиваются символами: *.jpeg, *.jpg, *.png, но есть исключение – ссылки на Яндекс.Диск. Они доступны "
    "в формате https://yadi.sk/i/qUXcCwzmryWINw или https://disk.yandex.ru/i/qUXcCwzmryWINw. Разделите ссылки пробелом или знаком переноса строки.\n\n"
    "Правильная ссылка:\n- не содержит дополнительных портов;\n- не ведет на HTML-страницу с изображением. Например, нельзя указывать ссылку на "
    "обзор товара, в котором есть фотографии;\n- не требует авторизации для доступа к изображению.\n\nСсылка на папку с изображениями\nМожно "
    "использовать ссылку на папку с изображениями на Я.Диске. Например, https://yadi.sk/d/qUXcCwzmryWINw или https://disk.yandex.ru/d/qUXcCwzmryWINw\n\n"
    "В качестве дополнительных фото будут использованы 14 изображений из папки.  Если вы хотите, чтобы картинки загрузились в нужном порядке, "
    "пронумеруйте их названия. Например, «1», «2», «3» или «фото1», «фото2», «фото3».\n\n"
    "Подробнее о требованиях можно узнать в https://seller-edu.ozon.ru/work-with-goods/trebovaniya-k-kartochkam-tovarov/media/foto-i-video-tovara"
)

# ==================== 18 базовых колонок (фиксированы во всех категориях) ====================
OZON_BASE_COLUMNS = [
    ("№", "_row_num", False, "number", "", ""),
    ("Артикул", "article", True, "text",
     "Введите артикул товара или его номер в вашей базе. Артикул должен быть уникальным в рамках вашего "
     "ассортимента https://seller-edu.ozon.ru/docs/work-with-goods/trebovaniya-k-kartochkam-tovarov/articyl-tovara.html", ""),
    ("Название товара", "name", False, "text",
     "Ознакомьтесь с Требованиями к названию, чтобы указать правильное название товара и пройти модерацию. "
     "Вы можете не заполнять это поле — тогда название составится автоматически из обязательных характеристик: "
     "тип + бренд + модель + важные характеристики для категории "
     "https://seller-edu.ozon.ru/libra/work-with-goods/trebovaniya-k-kartochkam-tovarov/product-information/nazvanie-tovara", G_NAME),
    ("Предельная цена без акций, руб.", "price", True, "number",
     "Цена, которую вы устанавливаете вручную https://seller-edu.ozon.ru/libra/ceny-i-akcii/rabota-s-cenami/price-control", G_PRICE),
    ("Зачёркнутая цена, руб.", "strike_price", False, "number",
     "Цена, которую покупатель видит зачёркнутой https://seller-edu.ozon.ru/libra/ceny-i-akcii/rabota-s-cenami/price-control", G_PRICE),
    ("НДС, %", "vat_rate", True, "select",
     "Укажите ставку НДС. Если товар не облагается НДС, или вы не платите НДС – укажите Не облагается "
     "https://seller-edu.ozon.ru/libra/work-with-goods/zagruzka-tovarov/creating-goods/sozdanie-tovarov-v-lk", G_PRICE),
    ("Рассрочка", "installment", False, "select",
     "Добавим товару пометку «Рассрочка 0–0–6» и будем отображать в специальных подборках. Дисконт удерживается "
     "только за проданные товары вместе с другими комиссиями, а Ozon сразу переводит вам полную стоимость товара. "
     "Редактировать список добавленных товаров можно в разделе «Цены и акции → Мои акции» ", G_PROMO),
    ("Ускоренный сбор отзывов", "reviews_boost", False, "select",
     "Подключим товару ускоренный сбор отзывов. Вы получите 10 отзывов с любым контентом: текст, фото, видео, или "
     "просто оценки. Стоимость за один отзыв или оценку — 250 ₽ ", G_PROMO),
    ("SKU", "sku_copy", False, "text",
     "Заполните поле, если хотите скопировать чужой товар, размещённый на Ozon. Тогда блоки справа можно не "
     "заполнять. Артикул должен быть уникальным. "
     "https://seller-edu.ozon.ru/libra/work-with-goods/zagruzka-tovarov/created-goods/uznat-sku-tovarov", G_SKU),
    ("Штрихкод (Серийный номер / EAN)", "barcode", False, "text",
     "Введите штрихкод товара от производителя и наклейте его на упаковку.\nЭто код, по которому товар принимают "
     "на складе. Поле обязательно для всех схем продаж. Без штрихкода не сможем выплатить компенсацию при утере "
     "https://seller-edu.ozon.ru/work-with-goods/trebovaniya-k-kartochkam-tovarov/product-information/rabota-so-shtrihkodami", G_SKU),
    ("ТН ВЭД коды ЕАЭС", "okpd_code", True, "select",
     "Выберите одно значение из списка. Если вы не знаете, какой код нужно указать, то вам необходимо обратиться "
     "к таможенной службе или таможенному представителю ", G_EXTRA),
    ("Вес в упаковке, г", "package_weight_grams", True, "number",
     "Можем взять дополнительную плату, если ОВХ отличаются от реальных. Укажите вес единицы товара в граммах "
     "вместе с упаковкой, в которой будете отправлять товар. Введите только число "
     "https://seller-edu.ozon.ru/libra/work-with-goods/trebovaniya-k-kartochkam-tovarov/product-information/ovh", G_EXTRA),
    ("Ширина упаковки, мм", "package_width_mm", True, "number",
     "Можем взять дополнительную плату, если ОВХ отличаются от реальных. Измерьте в миллиметрах любую сторону "
     "товара в упаковке, в которой будете отправлять. Изделия неправильной формы — от одного края до другого. "
     "Комплект из нескольких товаров сложите стопкой. Одежду, текстиль и наборы для вышивания сложите пополам "
     "в упаковке https://seller-edu.ozon.ru/docs/work-with-goods/trebovaniya-k-kartochkam-tovarov/ovh.html", G_EXTRA),
    ("Высота упаковки, мм", "package_height_mm", True, "number",
     "Можем взять дополнительную плату, если ОВХ отличаются от реальных. Измерьте в миллиметрах любую сторону "
     "товара в упаковке, в которой будете отправлять. Изделия неправильной формы — от одного края до другого. "
     "Комплект из нескольких товаров сложите стопкой. Одежду, текстиль и наборы для вышивания сложите пополам "
     "в упаковке https://seller-edu.ozon.ru/docs/work-with-goods/trebovaniya-k-kartochkam-tovarov/ovh.html", G_EXTRA),
    ("Длина упаковки, мм", "package_length_mm", True, "number",
     "Можем взять дополнительную плату, если ОВХ отличаются от реальных. Измерьте в миллиметрах любую сторону "
     "товара в упаковке, в которой будете отправлять. Изделия неправильной формы — от одного края до другого. "
     "Комплект из нескольких товаров сложите стопкой. Одежду, текстиль и наборы для вышивания сложите пополам "
     "в упаковке https://seller-edu.ozon.ru/docs/work-with-goods/trebovaniya-k-kartochkam-tovarov/ovh.html", G_EXTRA),
    ("Ссылка на главное фото", "main_photo", True, "text", HINT_MAIN_PHOTO, G_EXTRA),
    ("Ссылки на дополнительные фото", "extra_photos", False, "text", HINT_EXTRA_PHOTOS, G_EXTRA),
    ("Артикул фото", "photo_article", False, "text",
     'Название файла с изображением товара.\n Запрещенные символы: "/" и "_". ', G_EXTRA),
]


# ========== Вспомогательные ==========

def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Zа-яА-Я]+", "_", name).strip("_")[:40] or "category"


def _norm(name: str) -> str:
    return re.sub(r"[^a-zа-я0-9]", "", (name or "").lower())


def _match_enum_case(value: str, values: list) -> str:
    low = (value or "").strip().lower()
    for v in values or []:
        if str(v).strip().lower() == low:
            return str(v)
    return (value or "").strip()


def _normalize_multi(value: str) -> str:
    parts = re.split(r"[;,]", value or "")
    return ";".join(p.strip() for p in parts if p.strip())


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
    return _norm(name) in { _norm(b) for b in BRAND_NAMES }


def _attr_group(attr: dict) -> str:
    """Группа-блок строки 1 для атрибутной колонки (как в официальных шаблонах)."""
    name = (attr.get("name") or "")
    if _is_brand_name(name) or "объедин" in name.lower():
        return G_UNION
    if (attr.get("group") or "") == "variant":
        return G_VARIANT
    return G_ATTRS


def _row3_marker(col: dict) -> Optional[str]:
    """Маркер строки 3: комбинация обязательности/рекомендации/множественного выбора/бренда."""
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
        base = (p.get("sku") or p.get("external_id") or f"ID{p.get('id')}")
        count = seen.get(base, 0) + 1
        seen[base] = count
        p["_article"] = base if count == 1 else f"{base}_{count}"


# ========== Значения ячеек ==========

def _cell_value(product: dict, col: dict, attr_map: dict, row_num: int):
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
    if key in ("package_weight_grams", "package_width_mm", "package_height_mm", "package_length_mm"):
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
        # Фолбэк-синонимы для бренда/модели (если атрибут сохранён под другим именем)
        if raw in (None, "") and norm_key in ("brand", "model"):
            for syn in (["бренд", "брендводеждеиобуви"] if norm_key == "brand"
                        else ["названиемодели", "названиемоделидляобъединенияводнукарточку",
                              "объединитьнаоднойкарточке", "модель"]):
                if syn in attr_map and attr_map[syn] not in (None, ""):
                    raw = attr_map[syn]
                    break
        if raw in (None, "") and norm_key == "model":
            raw = product.get("name")          # название модели = название товара
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


# ========== Сборка книги Ozon ==========

def build_ozon_workbook(products: list, spec: Optional[dict]) -> Workbook:
    """Шапка 1:1 с официальным шаблоном категории: база 18 колонок + атрибуты спека по порядку."""
    _unique_articles(products)

    wb = Workbook()
    ws = wb.active
    ws.title = "Шаблон"

    columns = []
    for header, key, required, ctype, hint, group in OZON_BASE_COLUMNS:
        columns.append({
            "header": header, "key": key, "required": required, "type": ctype,
            "hint": hint, "group": group, "values": None, "multi": False,
            "max_count": None, "is_brand": False, "recommended": False,
        })
    for col in columns:
        if col["key"] == "vat_rate":
            col["values"] = ["Не облагается", "22", "10", "7", "5"]
        elif col["key"] in ("installment", "reviews_boost"):
            col["values"] = ["Да", "Нет"]

    # ✅ Атрибутные колонки — СТРОГО в порядке спека категории (как в официальном шаблоне)
    for a in (spec or {}).get("attributes") or []:
        name = a.get("name") or ""
        if not name:
            continue
        norm = _norm(name)
        recommended = norm in RECOMMENDED_ONLY
        required = bool(a.get("required")) and not recommended
        columns.append({
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
        })

    columns.append({"header": "Ошибка", "key": None, "required": False, "recommended": False,
                    "type": "text", "hint": "Критичная ошибка в характеристиках товара. "
                    "Товар с ошибками не будет продаваться. ", "group": "", "values": None,
                    "multi": False, "max_count": None, "is_brand": False})
    columns.append({"header": "Недочёты", "key": None, "required": False, "recommended": False,
                    "type": "text", "hint": "Устаревшее или незаполненное значение в характеристиках товара. "
                    "Возникает при изменениях в атрибутной модели и не влияет на продажу товара. ",
                    "group": "", "values": None, "multi": False, "max_count": None, "is_brand": False})

    used_dicts = {}
    last_row = max(DATA_START_ROW + len(products) - 1, DATA_START_ROW) + 50

    # ---------- 4 строки шапки ----------
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
            hint = "Выберите значение из списка. Примеры: " + "; ".join(str(v) for v in col["values"][:5])
        ws.cell(row=4, column=idx, value=hint or None)

        if col["values"]:
            rng = f"{letter}{DATA_START_ROW}:{letter}{last_row}"
            if len(col["values"]) <= 8 and all(len(str(v)) < 20 for v in col["values"]):
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

    # ---------- Данные с 5-й строки ----------
    for r, product in enumerate(products, start=DATA_START_ROW):
        attr_map = {_norm(a.get("name")): a.get("value") for a in (product.get("attributes") or []) if a.get("name")}
        for idx, col in enumerate(columns, start=1):
            value = _cell_value(product, col, attr_map, row_num=r - DATA_START_ROW + 1)
            if value is None or value == "":
                continue
            ws.cell(row=r, column=idx, value=value)

    # ---------- Дополнительные листы ----------
    _build_extra_sheet(wb, "Озон.Видео", "Озон.Видео", [
        ("Артикул", True, ""),
        ("Озон.Видео: название", False, "Укажите название для видео "),
        ("Озон.Видео: ссылка", False,
         "Укажите ссылку на видео (MP4, MOV). Продолжительность от 8 сек до 5 минут, размер файла не более 2ГБ "),
        ("Озон.Видео: товары на видео", False,
         "Укажите товары, которые демонстрируются в вашем видео. Перечислите SKU через запятую (не более 5). "),
    ])
    _build_extra_sheet(wb, "Озон.Видеообложка", "Озон.Видеообложка", [
        ("Артикул", True, ""),
        ("Озон.Видеообложка: ссылка", False,
         "Укажите ссылку на видео (MP4, MOV). Продолжительность от 8 до 30 секунд, размер файла не более 20МБ "),
    ])
    _build_extra_sheet(wb, "Документация PDF", "Документация PDF", [
        ("Артикул", True, ""),
        ("Название файла PDF", False, ""),
        ("Документ PDF", False, "Прямая ссылка на PDF-файл: он должен открываться и скачиваться по ссылке. "),
    ])

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


# ========== Сборка книг Yandex / WB ==========

def build_simple_workbook(platform: str, products: list, spec: Optional[dict]) -> Workbook:
    _unique_articles(products)
    wb = Workbook()
    ws = wb.active
    ws.title = "Список товаров" if platform == "yandex" else "Товары"

    columns = [
        {"header": "Артикул", "key": "article", "required": True, "type": "text", "values": None, "multi": False},
        {"header": "Название", "key": "name", "required": True, "type": "text", "values": None, "multi": False},
        {"header": "Цена", "key": "price", "required": True, "type": "number", "values": None, "multi": False},
        {"header": "Категория", "key": "category", "required": False, "type": "text", "values": None, "multi": False},
        {"header": "Штрихкод", "key": "barcode", "required": False, "type": "text", "values": None, "multi": True},
    ]
    for a in (spec or {}).get("attributes") or []:
        columns.append({
            "header": a["name"], "key": f"attr:{_norm(a['name'])}",
            "required": bool(a.get("required")), "type": a.get("type", "text"),
            "values": a.get("values"), "multi": a.get("type") == "multiselect",
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
                dv = DataValidation(type="list", formula1='"' + ",".join(str(v) for v in col["values"]) + '"',
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
        attr_map = {_norm(a.get("name")): a.get("value") for a in (product.get("attributes") or []) if a.get("name")}
        for idx, col in enumerate(columns, start=1):
            value = _cell_value(product, col, attr_map, row_num=r - 1)
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


# ========== Оркестратор ==========

def generate_export(products: list, specs_by_category: dict, platform: str):
    """
    Возвращает (bytes, filename).
    ✅ Приоритет: эталонный шаблон Ozon, загруженный пользователем, — файл-каркас
       заполняется товарами (формат 1:1 с кабинетом).
    Иначе: генерация из спека категории. Несколько категорий → zip.
    """
    from services.template_filler import fill_official_template, has_official_template

    groups = {}
    for p in products:
        cat = p.get("mapped_category") or p.get("category") or "Без категории"
        groups.setdefault(cat, []).append(p)

    files = []
    for cat, prods in groups.items():
        if platform == "ozon" and has_official_template(cat):
            files.append((f"{platform}_{_slug(cat)}",
                          fill_official_template(cat, prods, specs_by_category.get(cat))))
            continue
        spec = specs_by_category.get(cat)
        wb = build_ozon_workbook(prods, spec) if platform == "ozon" \
            else build_simple_workbook(platform, prods, spec)
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