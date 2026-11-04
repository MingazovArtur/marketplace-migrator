"""Билдер книги Яндекс Маркета (лист «Список товаров» + инструкция)."""

import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from services.xlsx_generator.columns import (
    CELL_BORDER,
    DATA_FONT,
    GRAY_FILL,
    GROUP_FONT,
    HEADER_FONT,
    HINT_FONT,
    RED_HEADER_FONT,
    YANDEX_GROUP_MERGES,
    YANDEX_TEMPLATE_COLUMNS,
    YM_HINT_FILL,
)
from services.xlsx_generator.common import _generate_ean13, _norm, _strip_html, _unique_articles


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

    for col_idx, (header, _key, required, is_gray, group_title, hint) in enumerate(
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
