"""Стили ячеек и общие константы структуры XLSX-шаблонов (Ozon / Яндекс Маркет).

Выделено из монолита services/xlsx_generator.py (E-7, неделя 4);
Р19 — разбиение columns.py (597 строк) на под-пакет.
"""

from openpyxl.styles import Border, Font, PatternFill, Side

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
