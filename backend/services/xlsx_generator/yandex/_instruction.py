"""Лист «Инструкция» книги Яндекс Маркета (1-й лист шаблона).

Вынесено без изменений из монолита services/xlsx_generator/yandex.py (Р23).
"""

from openpyxl.styles import Alignment, Font, PatternFill


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
        ("Подробные рекомендации по заполнению полей см. на листе «Описание полей»", link_font, 22),
        (
            "Одна строка на листе Список товаров должна соответствовать одному вашему товару.",
            text_font,
            22,
        ),
        (
            "На листе Список товаров нельзя: изменять названия полей, удалять столбцы, менять их местами.",
            text_font,
            22,
        ),
        (
            "В шаблоне нельзя: изменять названия листов, удалять листы, менять их местами.",
            text_font,
            22,
        ),
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
