"""Сканирование книги XLSX: поиск листа данных, строки заголовков, строки данных,
колонок произвольных характеристик AliExpress."""

from services.template_filler._common import _norm


def _find_data_sheet(wb):
    """Находит рабочий лист с товарами в книге любой площадки."""
    for candidate in (
        "Список товаров",
        "Шаблон",
        "Товары",
        "Офферы",
        "Шаблон Поставщика",
        "Assortment",
        "Каталог",
    ):
        if candidate in wb.sheetnames:
            return wb[candidate]
    skip_words = (
        "инструкция",
        "описание полей",
        "справочник",
        "видео",
        "документация",
        "правила",
        "требования к изображениям",
        "readme",
        "help",
    )
    for name in wb.sheetnames:
        if not any(w in name.lower() for w in skip_words):
            return wb[name]
    return wb.active


def _find_header_row(ws) -> int | None:
    """
    Ищет строку заголовков по ключевым колонкам площадок:
    - Ozon / WB / Магнит / Холодильник: «Артикул», «Ваш SKU *», «Артикул продавца»
    - Мегамаркет: «Код товара продавца», «Основной штрихкод (GTIN)»
    - AliExpress: «Модель (seller SPU ID)*», «Артикул/Штрихкод (seller SKU ID)*»
    """
    header_markers = {
        "артикул",
        "вашsku",
        "артикулпродавца",
        "артикулsku",
        "кодтоварапродавца",
        "кодтоварапродавцаofferid",
        "основнойштрихкодgtin",
        "модельsellerspuid",
        "артикулштрихкодsellerskuid",
        "sellerskuid",
        "sellerspuid",
        "offerid",
        "sku",
        "наименование",
        "наименованиетовара",
        "названиетовара",
    }
    for row in range(1, 12):
        for cell in ws[row]:
            if cell.value:
                norm_val = _norm(str(cell.value).rstrip("*"))
                if norm_val in header_markers:
                    return row
    return None


def _detect_data_start_row(ws, header_row: int, platform: str) -> int:
    """
    Определяет строку, с которой начинаются данные товаров:
    - AliExpress: строка 1 — блоки, строка 2 — подсказки, строка 3 — заголовки (`header_row = 3`),
      данные начинаются со строки 4 (`header_row + 1`).
    - Мегамаркет: если заголовки в 1-й строке — данные со 2-й строки (`header_row + 1`).
    - Яндекс Маркет: строка 2 — заголовки, строка 3 — подсказки, строка 4 — данные (`header_row + 2`).
    - Ozon: строка 2 — заголовки, строка 3 — «Обязательное поле», строка 4 — подсказки, строка 5 — данные (`header_row + 3`).
    """
    if platform == "aliexpress":
        return header_row + 1

    if platform == "yandex":
        return header_row + 2

    row_plus_1_text = " ".join(
        str(c.value).lower() for c in ws[header_row + 1] if c.value is not None
    )
    if "обязательное поле" in row_plus_1_text or "рекомендуем к заполнению" in row_plus_1_text:
        return header_row + 3

    if any(
        m in row_plus_1_text
        for m in (
            "уникальный идентификатор",
            "значение поля выгружено",
            "заполняется автоматически",
            "обязательный параметр",
            "необязательный параметр",
            "уникальный код товара",
        )
    ):
        return header_row + 2

    if platform == "megamarket":
        return header_row + 1

    return header_row + 1 if header_row in (1, 3) else 5


def _detect_aliexpress_custom_attr_cols(ws, header_row: int) -> list[int]:
    """
    Находит до 5 столбцов блока «Произвольные характеристики продавца» в шаблоне AliExpress
    (по тексту «Добавьте произвольную характеристику» в строке подсказок header_row - 1).
    """
    custom_cols: list[int] = []
    if header_row < 2:
        return custom_cols
    hint_row = header_row - 1
    for col in range(1, ws.max_column + 1):
        hint_val = str(ws.cell(row=hint_row, column=col).value or "").lower()
        if "произвольную характеристику" in hint_val:
            custom_cols.append(col)
    return custom_cols[:5]
