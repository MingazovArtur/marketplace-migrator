"""
Парсер файлов маркетплейсов (Магнит Маркет, Ozon, Wildberries, Яндекс Маркет).
Поддерживает форматы: XLSX, CSV.

Для Магнит Маркета — специальный парсер, который:
  - находит лист с товарами (пропуская служебные листы: Инструкция, Бренды и т.д.),
  - пропускает маркерные строки ("Не менять", "---"),
  - обрабатывает каждую строку как отдельный SKU (вариант) для массового обновления,
  - фото разбивает по ';' или ','.
"""
import io
import re
import logging
from typing import Dict, List, Optional, Any
import pandas as pd

logger = logging.getLogger(__name__)

# Маркерные строки, которые нужно пропускать в файлах Магнит Маркета
MAGNIT_SERVICE_MARKERS = [
    "не менять",
    "не изменяйте",
    "---",
    "заполните",
    "обязательное поле",
    "пример заполнения",
]

# Маппинг колонок для разных платформ
COLUMN_MAPPINGS = {
    "ozon": {
        "name": ["Название товара", "Название", "Наименование"],
        "price": ["Цена", "Цена, руб", "Цена продажи", "Стоимость"],
        "sku": ["Артикул", "Артикул продавца", "Артикул продавца (внутренний)"],
        "category": ["Категория", "Раздел"],
        "photo": ["Ссылка на фото", "Фото", "Ссылки на фото"],
        "desc": ["Описание"],
        "brand": ["Бренд"],
        "stock": ["Остаток"],
    },
    "wildberries": {
        "name": ["Название товара", "Название", "Наименование"],
        "price": ["Цена", "Цена, руб", "Цена продажи", "Стоимость"],
        "sku": ["Артикул", "Артикул продавца", "Баркод"],
        "category": ["Категория", "Раздел", "Предмет"],
        "photo": ["Ссылка на фото", "Фото", "Ссылки на фото"],
        "desc": ["Описание"],
        "brand": ["Бренд"],
        "stock": ["Остаток"],
    },
    "yandex": {
        "name": ["Название товара", "Название", "Наименование"],
        "price": ["Цена", "Цена, руб", "Цена продажи", "Стоимость"],
        "sku": ["Артикул", "Артикул продавца"],
        "category": ["Категория", "Раздел"],
        "photo": ["Ссылка на фото", "Фото", "Ссылки на фото"],
        "desc": ["Описание"],
        "brand": ["Бренд"],
        "stock": ["Остаток"],
    },
    "magnit": {
        "name": ["Название товара", "Название", "Наименование"],
        "price": ["Цена", "Цена, руб", "Цена продажи"],
        "sku": ["Seller SKU ID", "SellerSKU", "SKU ID", "Артикул продавца", "Артикул"],
        "external_id": ["Product ID", "Продукт ID", "ID товара"],
        "group_id": ["Продавец ID", "Seller ID"],
        "barcode": ["ШК", "Баркод", "Штрихкод"],
        "category": ["Категория", "Раздел"],
        "photo": ["Фото (общее)", "Фото", "Ссылка на фото", "Ссылки на фото"],
        "photo_sku": ["Фото SKU"],
        "desc": ["Описание товара", "Описание"],
        "short_desc": ["Краткое описание"],
        "attrs": ["Свойства товара", "Свойства", "Характеристики"],
        "brand": ["Бренд"],
        "stock": ["Остаток"],
        "okpd2": ["ОКПД2"],
        "tn_ved": ["ТН ВЭД", "ТНВЭД"],
    },
}


# ==================== Вспомогательные функции ====================

def _clean_value(value: Any) -> str:
    """Очищает значение от пробелов и приводит к строке. Пустые/NaN -> ''."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _find_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    """
    Ищет колонку по списку возможных названий.
    Сначала ищет точное совпадение (без учета регистра), затем — по подстроке.
    """
    col_lower_map = {str(c).lower().strip(): str(c) for c in columns}

    # Точное совпадение
    for candidate in candidates:
        key = candidate.lower().strip()
        if key in col_lower_map:
            return col_lower_map[key]

    # Нечеткий поиск: колонка содержит кандидат как подстроку
    for candidate in candidates:
        candidate_lower = candidate.lower().strip()
        for col_lower, col_orig in col_lower_map.items():
            if candidate_lower in col_lower:
                return col_orig

    return None


def _split_photos(photo_str: str) -> List[str]:
    """Разбивает строку с фото по ';' или ',' и возвращает список ссылок."""
    if not photo_str:
        return []
    parts = re.split(r"[;,]", photo_str)
    photos = []
    for part in parts:
        part = part.strip()
        if part and (part.startswith("http://") or part.startswith("https://")):
            photos.append(part)
    return photos


def _parse_price(price_str: str) -> float:
    """Парсит цену из строки: убирает пробелы, символы валют, заменяет запятую на точку."""
    if not price_str:
        return 0.0
    cleaned = (
        price_str
        .replace(" ", "")
        .replace("\u00a0", "")
        .replace("₽", "")
        .replace("руб.", "")
        .replace("руб", "")
        .replace(",", ".")
    )
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_stock(stock_str: str) -> int:
    """Парсит остаток из строки."""
    if not stock_str:
        return 0
    cleaned = stock_str.replace(" ", "").replace(",", "")
    try:
        return int(float(cleaned))
    except ValueError:
        return 0


# ==================== Парсер Магнит Маркет ====================

def _parse_magnit(file_content: bytes) -> Dict:
    """
    Парсер файла Магнит Маркет («Массовое обновление карточек»).
    Каждая строка в таком файле — это независимый SKU, поэтому мы импортируем каждую строку отдельно.
    """
    xls = pd.ExcelFile(io.BytesIO(file_content))

    # --- Шаг 1: ищем лист с данными ---
    data_sheet = None
    skip_keywords = ["инструкция", "бренд", "справочник", "шаблон", "пример"]

    for sheet_name in xls.sheet_names:
        sheet_lower = sheet_name.lower()
        # Пропускаем служебные листы
        if any(skip in sheet_lower for skip in skip_keywords):
            continue

        # Читаем первые 30 строк для поиска заголовков
        try:
            df_tmp = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=30)
        except Exception:
            continue

        # Ищем строку заголовков
        for _, row in df_tmp.iterrows():
            row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
            # Пропускаем маркерные строки
            if any(marker in row_text for marker in ["не менять", "не изменяйте"]):
                continue
            # Ищем заголовки товаров
            if "название товара" in row_text or ("название" in row_text and "артикул" in row_text):
                data_sheet = sheet_name
                break

        if data_sheet:
            break

    if data_sheet is None:
        raise ValueError(
            "Не найден лист с данными товаров в файле Магнит Маркета. "
            "Убедитесь, что файл содержит лист с товарами (например, 'SKU')."
        )

    # --- Шаг 2: читаем весь лист без заголовков ---
    df = pd.read_excel(xls, sheet_name=data_sheet, header=None)

    # --- Шаг 3: находим строку заголовков ---
    header_row_idx = None
    for idx, row in df.iterrows():
        row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        # Пропускаем маркерные строки
        if any(marker in row_text for marker in ["не менять", "не изменяйте"]):
            continue
        # Ищем заголовки
        if "название товара" in row_text or ("название" in row_text and "артикул" in row_text):
            header_row_idx = idx
            break

    if header_row_idx is None:
        raise ValueError("Не найдена строка заголовков в файле Магнит Маркета")

    # --- Шаг 4: формируем заголовки и данные ---
    header_row = df.iloc[header_row_idx]
    headers = [
        str(v).strip() if pd.notna(v) else f"col_{i}"
        for i, v in enumerate(header_row.values)
    ]

    data = df.iloc[header_row_idx + 1:].copy()
    data.columns = headers

    # --- Шаг 5: фильтруем служебные и пустые строки ---
    filtered_rows = []
    for _, row in data.iterrows():
        row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        # Пропускаем маркерные строки (включая "---" и "не менять" из подвала файла)
        if any(marker in row_text for marker in MAGNIT_SERVICE_MARKERS):
            continue
        # Пропускаем пустые строки
        non_empty = [str(v).strip() for v in row.values if pd.notna(v) and str(v).strip()]
        if not non_empty:
            continue
        filtered_rows.append(row)

    if not filtered_rows:
        return {
            "products": [],
            "errors": [],
            "warnings": [{"type": "empty", "message": "Файл не содержит данных о товарах"}],
            "total_rows": 0,
            "imported": 0,
            "failed": 0,
        }

    filtered_df = pd.DataFrame(filtered_rows)

    # --- Шаг 6: определяем колонки ---
    mapping = COLUMN_MAPPINGS["magnit"]
    cols = filtered_df.columns.tolist()

    name_col        = _find_column(cols, mapping["name"])
    price_col       = _find_column(cols, mapping["price"])
    sku_col         = _find_column(cols, mapping["sku"])          # Seller SKU ID
    external_id_col = _find_column(cols, mapping["external_id"])  # Product ID
    barcode_col     = _find_column(cols, mapping["barcode"])      # ШК
    category_col    = _find_column(cols, mapping["category"])
    photo_col       = _find_column(cols, mapping["photo"])
    photo_sku_col   = _find_column(cols, mapping.get("photo_sku", []))
    desc_col        = _find_column(cols, mapping["desc"])
    short_desc_col  = _find_column(cols, mapping["short_desc"])
    brand_col       = _find_column(cols, mapping["brand"])
    stock_col       = _find_column(cols, mapping["stock"])
    okpd2_col       = _find_column(cols, mapping["okpd2"])
    tn_ved_col      = _find_column(cols, mapping["tn_ved"])

    if not name_col:
        raise ValueError("Не найдена колонка 'Название товара' в файле Магнит Маркета")

    logger.info(
        f"Магнит: name={name_col!r}, sku={sku_col!r}, "
        f"product_id={external_id_col!r}, photo={photo_col!r}, photo_sku={photo_sku_col!r}"
    )

    # --- Шаг 7: парсим строки ---
    # ВАЖНО: В файле Магнита для массового обновления каждая строка — это отдельный SKU.
    # Мы НЕ группируем их с потерей данных, а импортируем каждую строку как самостоятельную единицу.
    products: List[Dict] = []
    errors: List[Dict] = []

    for idx, row in filtered_df.iterrows():
        row_num = idx + 2

        name = _clean_value(row.get(name_col))
        if not name:
            errors.append({"row": row_num, "error": "Пустое название товара"})
            continue

        # Цена
        price = _parse_price(_clean_value(row.get(price_col))) if price_col else 0.0

        # Фото (общее) + фото SKU
        photos: List[str] = []
        if photo_col:
            photos.extend(_split_photos(_clean_value(row.get(photo_col))))
        if photo_sku_col:
            photos.extend(_split_photos(_clean_value(row.get(photo_sku_col))))
        photos = list(dict.fromkeys(photos))[:10]  # уникализируем, максимум 10

        # Описание: полное, иначе краткое
        description = _clean_value(row.get(desc_col)) if desc_col else ""
        if not description and short_desc_col:
            description = _clean_value(row.get(short_desc_col))

        # SKU: Seller SKU ID → фолбэк ШК
        sku = _clean_value(row.get(sku_col)) if sku_col else ""
        if not sku and barcode_col:
            sku = _clean_value(row.get(barcode_col))

        product = {
            "name": name,
            "price": price,
            "sku": sku,
            "external_id": _clean_value(row.get(external_id_col)) if external_id_col else "",
            "barcode": _clean_value(row.get(barcode_col)) if barcode_col else "",
            "description": description,
            "photos": photos,
            "category": _clean_value(row.get(category_col)) if category_col else "Не указана",
            "brand": _clean_value(row.get(brand_col)) if brand_col else "",
            "stock": _parse_stock(_clean_value(row.get(stock_col))) if stock_col else 0,
            "okpd2": _clean_value(row.get(okpd2_col)) if okpd2_col else "",
            "tn_ved": _clean_value(row.get(tn_ved_col)) if tn_ved_col else "",
        }

        products.append(product)

    # --- Шаг 8: предупреждения ---
    warnings = []
    if products and all(p["price"] == 0 for p in products):
        warnings.append({
            "type": "magnit_no_price",
            "message": (
                "В файле Магнит Маркета нет цен или все цены равны 0. "
                "Задайте цены вручную после импорта."
            ),
        })

    return {
        "products": products,
        "errors": errors,
        "warnings": warnings,
        "total_rows": len(filtered_rows),
        "imported": len(products),
        "failed": len(errors),
    }


# ==================== Парсер плоских файлов (Ozon, WB, Яндекс) ====================

def _parse_flat(file_content: bytes, platform: str, file_type: str) -> Dict:
    """Парсер плоских файлов (CSV / XLSX) для Ozon, Wildberries, Яндекс Маркета."""
    # Читаем файл
    if file_type == "csv":
        try:
            df = pd.read_csv(io.BytesIO(file_content))
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(io.BytesIO(file_content), encoding="windows-1251")
            except Exception:
                df = pd.read_csv(io.BytesIO(file_content), encoding="utf-8", errors="replace")
    else:
        df = pd.read_excel(io.BytesIO(file_content))

    if df.empty:
        return {
            "products": [],
            "errors": [],
            "warnings": [{"type": "empty", "message": "Файл пуст"}],
            "total_rows": 0,
            "imported": 0,
            "failed": 0,
        }

    columns = [str(c).strip() for c in df.columns.tolist()]
    df.columns = columns

    mapping = COLUMN_MAPPINGS.get(platform, COLUMN_MAPPINGS["ozon"])

    name_col = _find_column(columns, mapping["name"])
    price_col = _find_column(columns, mapping["price"])
    sku_col = _find_column(columns, mapping["sku"])
    category_col = _find_column(columns, mapping["category"])
    photo_col = _find_column(columns, mapping["photo"])
    desc_col = _find_column(columns, mapping["desc"])
    brand_col = _find_column(columns, mapping["brand"])
    stock_col = _find_column(columns, mapping["stock"])

    if not name_col:
        raise ValueError(f"Не найдена колонка с названием товара для платформы '{platform}'")

    products: List[Dict] = []
    errors: List[Dict] = []

    for idx, row in df.iterrows():
        row_num = idx + 2  # +2: строка заголовков = 1, индексация с 0

        name = _clean_value(row.get(name_col))
        if not name:
            errors.append({"row": row_num, "error": "Пустое название товара"})
            continue

        # Цена
        price = 0.0
        if price_col:
            price_str = _clean_value(row.get(price_col))
            price = _parse_price(price_str)

        # Фото
        photos = []
        if photo_col:
            photo_str = _clean_value(row.get(photo_col))
            photos = _split_photos(photo_str)

        # Описание
        description = _clean_value(row.get(desc_col)) if desc_col else ""

        # Категория
        category = _clean_value(row.get(category_col)) if category_col else "Не указана"

        # Бренд
        brand = _clean_value(row.get(brand_col)) if brand_col else ""

        # Остаток
        stock = 0
        if stock_col:
            stock_str = _clean_value(row.get(stock_col))
            stock = _parse_stock(stock_str)

        # Артикул
        sku = _clean_value(row.get(sku_col)) if sku_col else ""

        product = {
            "name": name,
            "price": price,
            "sku": sku,
            "description": description,
            "photos": photos,
            "category": category,
            "brand": brand,
            "stock": stock,
        }
        products.append(product)

    return {
        "products": products,
        "errors": errors,
        "warnings": [],
        "total_rows": len(df),
        "imported": len(products),
        "failed": len(errors),
    }


# ==================== Точка входа ====================

def parse_file(file_content: bytes, platform: str, file_type: str) -> Dict:
    """
    Точка входа для парсинга файла маркетплейса.
    """
    platform = platform.lower().strip()

    # Магнит Маркет — только XLSX, специальный парсер
    if platform == "magnit":
        if file_type != "xlsx":
            raise ValueError("Для Магнит Маркета поддерживается только формат XLSX")
        return _parse_magnit(file_content)

    # Остальные платформы — плоские файлы
    if platform not in COLUMN_MAPPINGS:
        raise ValueError(f"Неизвестная платформа: {platform}")

    return _parse_flat(file_content, platform, file_type)


def preview_file(file_content: bytes, platform: str, file_type: str, max_rows: int = 10) -> Dict:
    """
    Возвращает превью первых строк файла для предпросмотра перед импортом.
    """
    # Парсим файл
    result = parse_file(file_content, platform, file_type)

    products = result.get("products", [])
    preview = products[:max_rows]

    # Определяем колонки из первого продукта
    columns = []
    if preview:
        columns = list(preview[0].keys())

    return {
        "columns": columns,
        "preview": preview,
        "total_estimated": result.get("total_rows", len(products)),
        "valid_estimated": result.get("imported", len(products)),
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
    }