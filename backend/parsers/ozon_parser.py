"""
Парсер импорта товаров из Excel-файлов Ozon.

Особенности файлов Ozon:
- Первые строки содержат заголовки и описания
- Несколько листов (Шаблон, Озон.Видео, Документация PDF)
- Данные о товарах начинаются с определенной строки
- Нужно пропускать служебные строки с инструкциями
"""
import re
from typing import List, Dict, Optional, Any, Tuple
from openpyxl import load_workbook


def parse_ozon_excel(file_path: str) -> Tuple[List[Dict[str, Any]], List[Dict]]:
    """
    Парсит Excel-файл экспорта Ozon и возвращает список товаров и ошибки.
    
    Args:
        file_path: Путь к Excel-файлу
        
    Returns:
        Кортеж (список товаров, список ошибок)
    """
    wb = load_workbook(file_path, data_only=True)
    
    # Ищем лист с данными о товарах
    sheet_name = None
    for name in wb.sheetnames:
        if name in ['Товары', 'Шаблон', 'Products', 'Template']:
            sheet_name = name
            break
    
    if not sheet_name:
        sheet_name = wb.sheetnames[0]  # Берем первый лист
    
    ws = wb[sheet_name]
    
    # Находим строку с заголовками колонок
    # Ищем строку, где есть "Артикул" или "Название товара"
    header_row = None
    for row_idx in range(1, min(30, ws.max_row + 1)):  # Ищем в первых 30 строках
        row_values = [str(cell.value or '').strip() for cell in ws[row_idx] if cell.value]
        row_str = ' '.join(row_values).lower()
        
        if 'артикул' in row_str or 'название товара' in row_str:
            header_row = row_idx
            break
    
    if not header_row:
        wb.close()
        raise ValueError("Не удалось найти заголовки колонок в файле. Убедитесь, что файл содержит стандартные колонки Ozon.")
    
    # Создаем маппинг колонок
    headers = {}
    header_cells = list(ws[header_row])
    for col_idx, cell in enumerate(header_cells, 1):
        if cell and cell.value:
            col_name = str(cell.value).strip().lower()
            headers[col_name] = col_idx
    
    # Определяем колонки (ищем по разным возможным названиям)
    col_article = find_column(headers, ['артикул', 'article', 'sku'])
    col_name = find_column(headers, ['название товара', 'название', 'name', 'product_name'])
    col_price = find_column(headers, ['предельная цена', 'цена на сайте', 'price', 'цена'])
    col_old_price = find_column(headers, ['зачёркнутая цена', 'old_price'])
    col_vat = find_column(headers, ['ндс', 'vat', 'ндс, %', 'размер ндс'])
    col_photo = find_column(headers, ['ссылка на главное фото', 'фото', 'photo', 'main_photo'])
    col_category = find_column(headers, ['категория', 'category'])
    col_type = find_column(headers, ['тип', 'type'])
    col_brand = find_column(headers, ['бренд', 'brand'])
    col_barcode = find_column(headers, ['штрихкод', 'barcode', 'ean', 'штрихкод (серийный номер'])
    col_weight = find_column(headers, ['вес в упаковке', 'вес', 'weight'])
    col_width = find_column(headers, ['ширина упаковки', 'ширина', 'width'])
    col_height = find_column(headers, ['высота упаковки', 'высота', 'height'])
    col_length = find_column(headers, ['длина упаковки', 'длина', 'length'])
    col_okpd = find_column(headers, ['тн вэд', 'okpd', 'тн вэд коды'])
    col_description = find_column(headers, ['аннотация', 'описание', 'description'])
    
    # Читаем данные о товарах
    products = []
    errors = []
    max_row = ws.max_row
    
    for row_idx in range(header_row + 1, max_row + 1):
        row_data = {}
        
        # Получаем значение из ячейки
        def get_cell_value(col_idx: Optional[int]) -> Optional[str]:
            if not col_idx:
                return None
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell and cell.value is not None:
                value = str(cell.value).strip()
                return value if value else None
            return None
        
        # Извлекаем данные
        article = get_cell_value(col_article)
        name = get_cell_value(col_name)
        price = get_cell_value(col_price)
        old_price = get_cell_value(col_old_price)
        vat = get_cell_value(col_vat)
        photo = get_cell_value(col_photo)
        category = get_cell_value(col_category)
        product_type = get_cell_value(col_type)
        brand = get_cell_value(col_brand)
        barcode = get_cell_value(col_barcode)
        weight = get_cell_value(col_weight)
        width = get_cell_value(col_width)
        height = get_cell_value(col_height)
        length = get_cell_value(col_length)
        okpd = get_cell_value(col_okpd)
        description = get_cell_value(col_description)
        
        # Пропускаем пустые строки
        if not any([article, name, price]):
            continue
        
        # Проверяем, что это действительно товар, а не служебная строка
        # Пропускаем строки, где название содержит инструкции
        if name and any(keyword in name.lower() for keyword in [
            'ознакомьтесь', 'требования', 'обязательное поле', 
            'заполняйте только', 'изменить цену', 'цена, которую'
        ]):
            continue
        
        # Очищаем и преобразуем данные
        cleaned_product = {
            'sku': article or '',
            'external_id': article or '',
            'name': name or '',
            'price': clean_price(price),
            'old_price': clean_price(old_price),
            'vat_rate': clean_vat(vat),
            'main_photo': photo or '',
            'photos': [photo] if photo else [],
            'category': category or '',
            'product_type': product_type or '',
            'brand': brand or '',
            'barcode': barcode or '',
            'package_weight_grams': clean_number(weight),
            'package_width_mm': clean_number(width),
            'package_height_mm': clean_number(height),
            'package_length_mm': clean_number(length),
            'okpd_code': clean_okpd(okpd),
            'description': description or '',
        }
        
        # Валидация
        row_errors = []
        if not cleaned_product['name']:
            row_errors.append(f"Строка {row_idx}: Пустое название товара")
        
        if not cleaned_product['price'] or cleaned_product['price'] <= 0:
            row_errors.append(f"Строка {row_idx}: Неверная цена товара")
        
        if row_errors:
            errors.extend(row_errors)
            continue
        
        products.append(cleaned_product)
    
    wb.close()
    return products, errors


def find_column(headers: Dict[str, int], possible_names: List[str]) -> Optional[int]:
    """Находит номер колонки по возможным названиям."""
    for name in possible_names:
        for header_name, col_idx in headers.items():
            if name.lower() in header_name.lower():
                return col_idx
    return None


def clean_price(price_str: Optional[str]) -> float:
    """Очищает цену от разделителей и преобразует в float."""
    if not price_str:
        return 0.0
    
    # Удаляем пробелы, запятые, заменяем на точку
    cleaned = str(price_str).replace(' ', '').replace(',', '.').replace('₽', '').strip()
    
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def clean_vat(vat_str: Optional[str]) -> str:
    """Очищает НДС и приводит к стандартному формату."""
    if not vat_str:
        return 'none'
    
    vat_str = str(vat_str).strip().lower()
    
    # Маппинг значений
    vat_map = {
        'не облагается': 'none',
        'не облагается ндс': 'none',
        '0%': 'none',
        '0': 'none',
        '5%': '5',
        '5': '5',
        '10%': '10',
        '10': '10',
        '20%': '20',
        '20': '20',
        '22%': '22',
        '22': '22',
    }
    
    return vat_map.get(vat_str, vat_str.replace('%', ''))


def clean_number(num_str: Optional[str]) -> Optional[int]:
    """Очищает числовое значение и преобразует в int."""
    if not num_str:
        return None
    
    try:
        # Удаляем пробелы, заменяем запятую на точку
        cleaned = str(num_str).replace(' ', '').replace(',', '.')
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def clean_okpd(okpd_str: Optional[str]) -> Optional[str]:
    """Очищает код ТН ВЭД, оставляя только цифры."""
    if not okpd_str:
        return None
    
    # Извлекаем первые 10 цифр
    digits = re.sub(r'[^\d]', '', str(okpd_str))
    return digits[:10] if digits else None