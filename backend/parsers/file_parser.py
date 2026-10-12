"""
Парсер файлов маркетплейсов (Магнит Маркет, Ozon, Wildberries, Яндекс Маркет).
Поддерживает форматы: XLSX, CSV.

Для Ozon — специальный парсер, который:
  - динамически находит строку заголовков (пропуская служебные инструкции),
  - игнорирует строки с подсказками ("Обязательное поле", "Заполняйте только"),
  - корректно очищает цены, НДС, габариты и ТН ВЭД.

Для Магнит Маркета — специальный парсер, который:
  - находит лист с товарами (пропуская служебные листы),
  - пропускает маркерные строки,
  - обрабатывает каждую строку как отдельный SKU.
"""
import io
import re
import logging
from typing import Dict, List, Optional, Any

import pandas as pd
import openpyxl

logger = logging.getLogger(__name__)

# Маркерные строки, которые нужно пропускать в файлах Магнит Маркета и Ozon
SERVICE_MARKERS = [
    "не менять",
    "не изменяйте",
    "---",
    "заполняйте только",
    "обязательное поле",
    "пример заполнения",
    "ознакомьтесь с требованиями",
    "блок можно не заполнять",
    "для всех вариантов товара",
    "вы можете заполнить эти поля",
    "самые популярные способы",
    "цены и акции",
]

# Маппинг колонок для разных платформ
COLUMN_MAPPINGS = {
    "ozon": {
        "name": ["Название товара", "Название", "Наименование"],
        "price": ["Предельная цена без акций, руб.", "Цена на сайте, ₽", "Цена", "Стоимость"],
        "sku": ["Артикул", "Артикул*", "Артикул продавца"],
        "category": ["Категория", "Раздел"],
        "photo": ["Ссылка на главное фото", "Ссылка на главное фото*", "Фото"],
        "desc": ["Описание", "Аннотация"],
        "brand": ["Бренд", "Бренд*"],
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
    """Ищет колонку по списку возможных названий."""
    col_lower_map = {str(c).lower().strip(): str(c) for c in columns}

    for candidate in candidates:
        key = candidate.lower().strip()
        if key in col_lower_map:
            return col_lower_map[key]

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
        str(price_str)
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
    cleaned = str(stock_str).replace(" ", "").replace(",", "")
    try:
        return int(float(cleaned))
    except ValueError:
        return 0


def _clean_vat(vat_str: str) -> str:
    """Очищает НДС и приводит к стандартному формату."""
    if not vat_str:
        return "none"
    vat_str = str(vat_str).strip().lower()
    vat_map = {
        "не облагается": "none",
        "не облагается ндс": "none",
        "0%": "none",
        "0": "none",
        "5%": "5",
        "5": "5",
        "10%": "10",
        "10": "10",
        "20%": "20",
        "20": "20",
        "22%": "22",
        "22": "22",
    }
    return vat_map.get(vat_str, vat_str.replace("%", ""))


def _parse_int(val_str: str) -> Optional[int]:
    """Парсит целое число из строки (для габаритов и веса)."""
    if not val_str:
        return None
    try:
        return int(float(str(val_str).replace(",", ".").replace(" ", "")))
    except (ValueError, TypeError):
        return None


def _clean_okpd(okpd_str: str) -> Optional[str]:
    """Очищает код ТН ВЭД, оставляя только первые 10 цифр."""
    if not okpd_str:
        return None
    digits = re.sub(r"[^\d]", "", str(okpd_str))
    return digits[:10] if digits else None


# ==================== Парсер Ozon ====================

def _parse_ozon(file_content: bytes, file_type: str) -> Dict:
    """Специализированный парсер для сложных XLSX-файлов Ozon (шаблоны и отчеты)."""
    if file_type != "xlsx":
        raise ValueError("Для Ozon поддерживается только формат XLSX")
    
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
    except Exception as e:
        raise ValueError(f"Не удалось открыть XLSX файл: {e}")
    
    sheet_name = "Шаблон" if "Шаблон" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sheet_name]
    
    # 1. Находим строку заголовков (где есть и "Артикул", и "Название товара")
    header_row_idx = None
    for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=50, values_only=True)):
        row_text = " ".join(str(cell).lower() for cell in row if cell is not None)
        if "артикул" in row_text and "название товара" in row_text:
            header_row_idx = idx + 1  # 1-based index для openpyxl
            break
            
    if header_row_idx is None:
        raise ValueError("Не найдена строка заголовков (Артикул, Название товара) в файле Ozon")
    
    # 2. Извлекаем заголовки
    header_cells = list(ws[header_row_idx])
    headers = [str(cell.value).strip() if cell.value else f"col_{i}" for i, cell in enumerate(header_cells)]
    
    # 3. Маппинг колонок Ozon (расширенный для шаблонов и отчетов)
    ozon_mapping = {
        "name": ["название товара", "название"],
        "price": ["предельная цена без акций, руб.", "цена на сайте, ₽", "цена"],
        "old_price": ["зачёркнутая цена, руб."],
        "vat": ["ндс, %", "размер ндс, %"],
        "sku": ["артикул", "артикул*"],
        "external_id": ["sku", "ozon product id"],
        "barcode": ["штрихкод (серийный номер / ean)", "штрихкод"],
        "okpd": ["тн вэд коды еаэс*", "тн вэд коды еаэс"],
        "weight": ["вес в упаковке, г*", "вес в упаковке, г"],
        "width": ["ширина упаковки, мм*", "ширина упаковки, мм"],
        "height": ["высота упаковки, мм*", "высота упаковки, мм"],
        "length": ["длина упаковки, мм*", "длина упаковки, мм"],
        "photo": ["ссылка на главное фото*", "ссылка на главное фото"],
        "photos": ["ссылки на дополнительные фото"],
        "brand": ["бренд*", "бренд"],
        "type": ["тип*", "тип"],
        "category": ["категория"],
        "description": ["аннотация", "описание"],
    }
    
    col_indices = {}
    for key, candidates in ozon_mapping.items():
        for i, h in enumerate(headers):
            h_lower = h.lower().strip()
            if any(cand in h_lower for cand in candidates):
                col_indices[key] = i
                break
                
    if "name" not in col_indices or "sku" not in col_indices:
        raise ValueError("Не найдены обязательные колонки 'Артикул' или 'Название товара'")
        
    products = []
    errors = []
    
    # 4. Читаем строки данных, пропуская инструкции
    for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True), start=header_row_idx + 1):
        row_text = " ".join(str(cell).lower() for cell in row if cell is not None)
        
        # Пропускаем строки с подсказками и инструкциями
        if any(marker in row_text for marker in SERVICE_MARKERS):
            continue
            
        # Пропускаем полностью пустые строки
        if not any(cell for cell in row):
            continue
            
        def get_val(key):
            idx = col_indices.get(key)
            if idx is not None and idx < len(row):
                val = row[idx]
                return str(val).strip() if val is not None else ""
            return ""
            
        sku = get_val("sku")
        name = get_val("name")
        
        # Если нет ни артикула, ни названия — это хвост файла
        if not sku and not name:
            continue
            
        if not name:
            errors.append({"row": row_idx, "error": "Пустое название товара"})
            continue
            
        # Парсинг полей
        price = _parse_price(get_val("price"))
        
        photos = []
        main_photo = get_val("photo")
        if main_photo:
            photos.extend(_split_photos(main_photo))
        add_photos = get_val("photos")
        if add_photos:
            photos.extend(_split_photos(add_photos))
        photos = list(dict.fromkeys(photos))[:15]  # Уникализируем, макс 15
        
        product = {
            "name": name,
            "price": price,
            "sku": sku,
            "external_id": get_val("external_id") or sku,
            "barcode": get_val("barcode"),
            "description": get_val("description"),
            "photos": photos,
            "category": get_val("category") or "Не указана",
            "brand": get_val("brand"),
            "product_type": get_val("type"),
            "package_weight_grams": _parse_int(get_val("weight")),
            "package_width_mm": _parse_int(get_val("width")),
            "package_height_mm": _parse_int(get_val("height")),
            "package_length_mm": _parse_int(get_val("length")),
            "vat_rate": _clean_vat(get_val("vat")),
            "okpd_code": _clean_okpd(get_val("okpd")),
        }
        products.append(product)
        
    wb.close()
    
    return {
        "products": products,
        "errors": errors,
        "warnings": [],
        "total_rows": len(products) + len(errors),
        "imported": len(products),
        "failed": len(errors),
    }


# ==================== Парсер Магнит Маркет ====================

def _parse_magnit(file_content: bytes) -> Dict:
    """Парсер файла Магнит Маркет («Массовое обновление карточек»)."""
    xls = pd.ExcelFile(io.BytesIO(file_content))

    data_sheet = None
    skip_keywords = ["инструкция", "бренд", "справочник", "шаблон", "пример"]

    for sheet_name in xls.sheet_names:
        sheet_lower = sheet_name.lower()
        if any(skip in sheet_lower for skip in skip_keywords):
            continue

        try:
            df_tmp = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=30)
        except Exception:
            continue

        for _, row in df_tmp.iterrows():
            row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
            if any(marker in row_text for marker in ["не менять", "не изменяйте"]):
                continue
            if "название товара" in row_text or ("название" in row_text and "артикул" in row_text):
                data_sheet = sheet_name
                break

        if data_sheet:
            break

    if data_sheet is None:
        raise ValueError("Не найден лист с данными товаров в файле Магнит Маркета.")

    df = pd.read_excel(xls, sheet_name=data_sheet, header=None)

    header_row_idx = None
    for idx, row in df.iterrows():
        row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        if any(marker in row_text for marker in ["не менять", "не изменяйте"]):
            continue
        if "название товара" in row_text or ("название" in row_text and "артикул" in row_text):
            header_row_idx = idx
            break

    if header_row_idx is None:
        raise ValueError("Не найдена строка заголовков в файле Магнит Маркета")

    header_row = df.iloc[header_row_idx]
    headers = [str(v).strip() if pd.notna(v) else f"col_{i}" for i, v in enumerate(header_row.values)]

    data = df.iloc[header_row_idx + 1:].copy()
    data.columns = headers

    filtered_rows = []
    for _, row in data.iterrows():
        row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        if any(marker in row_text for marker in SERVICE_MARKERS):
            continue
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
    mapping = COLUMN_MAPPINGS["magnit"]
    cols = filtered_df.columns.tolist()

    name_col = _find_column(cols, mapping["name"])
    price_col = _find_column(cols, mapping["price"])
    sku_col = _find_column(cols, mapping["sku"])
    external_id_col = _find_column(cols, mapping["external_id"])
    barcode_col = _find_column(cols, mapping["barcode"])
    category_col = _find_column(cols, mapping["category"])
    photo_col = _find_column(cols, mapping["photo"])
    photo_sku_col = _find_column(cols, mapping.get("photo_sku", []))
    desc_col = _find_column(cols, mapping["desc"])
    short_desc_col = _find_column(cols, mapping["short_desc"])
    brand_col = _find_column(cols, mapping["brand"])
    stock_col = _find_column(cols, mapping["stock"])
    okpd2_col = _find_column(cols, mapping["okpd2"])
    tn_ved_col = _find_column(cols, mapping["tn_ved"])

    if not name_col:
        raise ValueError("Не найдена колонка 'Название товара' в файле Магнит Маркета")

    products: List[Dict] = []
    errors: List[Dict] = []

    for idx, row in filtered_df.iterrows():
        row_num = idx + 2
        name = _clean_value(row.get(name_col))
        if not name:
            errors.append({"row": row_num, "error": "Пустое название товара"})
            continue

        price = _parse_price(_clean_value(row.get(price_col))) if price_col else 0.0

        photos: List[str] = []
        if photo_col:
            photos.extend(_split_photos(_clean_value(row.get(photo_col))))
        if photo_sku_col:
            photos.extend(_split_photos(_clean_value(row.get(photo_sku_col))))
        photos = list(dict.fromkeys(photos))[:10]

        description = _clean_value(row.get(desc_col)) if desc_col else ""
        if not description and short_desc_col:
            description = _clean_value(row.get(short_desc_col))

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

    warnings = []
    if products and all(p["price"] == 0 for p in products):
        warnings.append({
            "type": "magnit_no_price",
            "message": "В файле Магнит Маркета нет цен или все цены равны 0. Задайте цены вручную после импорта.",
        })

    return {
        "products": products,
        "errors": errors,
        "warnings": warnings,
        "total_rows": len(filtered_rows),
        "imported": len(products),
        "failed": len(errors),
    }


# ==================== Парсер плоских файлов (WB, Яндекс) ====================

def _parse_flat(file_content: bytes, platform: str, file_type: str) -> Dict:
    """Парсер плоских файлов (CSV / XLSX) для Wildberries, Яндекс Маркета."""
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
        row_num = idx + 2
        name = _clean_value(row.get(name_col))
        if not name:
            errors.append({"row": row_num, "error": "Пустое название товара"})
            continue

        price = 0.0
        if price_col:
            price = _parse_price(_clean_value(row.get(price_col)))

        photos = []
        if photo_col:
            photos = _split_photos(_clean_value(row.get(photo_col)))

        description = _clean_value(row.get(desc_col)) if desc_col else ""
        category = _clean_value(row.get(category_col)) if category_col else "Не указана"
        brand = _clean_value(row.get(brand_col)) if brand_col else ""
        stock = _parse_stock(_clean_value(row.get(stock_col))) if stock_col else 0
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
    """Точка входа для парсинга файла маркетплейса."""
    platform = platform.lower().strip()

    if platform == "ozon":
        return _parse_ozon(file_content, file_type)
        
    if platform == "magnit":
        if file_type != "xlsx":
            raise ValueError("Для Магнит Маркета поддерживается только формат XLSX")
        return _parse_magnit(file_content)

    if platform not in COLUMN_MAPPINGS:
        raise ValueError(f"Неизвестная платформа: {platform}")

    return _parse_flat(file_content, platform, file_type)


def preview_file(file_content: bytes, platform: str, file_type: str, max_rows: int = 10) -> Dict:
    """Возвращает превью первых строк файла для предпросмотра перед импортом."""
    result = parse_file(file_content, platform, file_type)

    products = result.get("products", [])
    preview = products[:max_rows]

    columns = list(preview[0].keys()) if preview else []

    return {
        "columns": columns,
        "preview": preview,
        "total_estimated": result.get("total_rows", len(products)),
        "valid_estimated": result.get("imported", len(products)),
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
    }