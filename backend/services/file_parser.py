"""
Универсальный парсер Excel/CSV файлов для разных маркетплейсов
"""
import logging
import io
import pandas as pd
from typing import List, Dict, Optional
from models.schemas import Product

logger = logging.getLogger(__name__)

# Словарь соответствия названий колонок для разных платформ (ключевые слова для поиска)
COLUMN_MAPPINGS = {
    "ozon": {
        "name": ["название", "name", "наименование", "товар"],
        "price": ["цена", "price", "цена продажи", "текущая цена"],
        "sku": ["артикул", "sku", "offer id", "идентификатор"],
        "description": ["описание", "description", "rich-контент"],
        "photos": ["фото", "photo", "images", "ссылка на фото", "изображение"]
    },
    "wildberries": {
        "name": ["наименование", "название", "товар", "модель"],
        "price": ["цена", "цена с учетом скидок", "розничная цена"],
        "sku": ["артикул", "баркод", "sku", "идентификатор"],
        "description": ["описание", "характеристики"],
        "photos": ["фото", "ссылка на фото", "media"]
    },
    "yandex": {
        "name": ["название", "модель", "наименование товара"],
        "price": ["цена", "price", "стоимость"],
        "sku": ["артикул", "sku", "идентификатор товара", "offer id"],
        "description": ["описание", "description"],
        "photos": ["фото", "picture", "url картинки"]
    }
}

def _find_column(df_columns: List[str], keywords: List[str]) -> Optional[str]:
    """Ищет колонку в DataFrame по списку ключевых слов (нечеткий поиск)"""
    df_cols_lower = [str(col).lower().strip() for col in df_columns]
    for keyword in keywords:
        for col in df_cols_lower:
            if keyword in col:
                # Возвращаем оригинальное имя колонки
                original_index = df_cols_lower.index(col)
                return str(df_columns[original_index])
    return None

def parse_file(file_content: bytes, platform: str, file_type: str) -> List[Dict]:
    """
    Парсит Excel или CSV файл и возвращает список словарей в формате Product
    """
    try:
        if file_type == 'csv':
            # Пробуем разные кодировки для CSV
            try:
                df = pd.read_csv(io.BytesIO(file_content), encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(file_content), encoding='windows-1251')
        else:
            df = pd.read_excel(io.BytesIO(file_content))
        
        # Очищаем названия колонок от пробелов
        df.columns = df.columns.str.strip()
        original_columns = df.columns.tolist()
        
        mappings = COLUMN_MAPPINGS.get(platform, COLUMN_MAPPINGS["ozon"])
        products = []
        
        for index, row in df.iterrows():
            # Ограничим импорт первыми 100 товарами для демо-безопасности
            if len(products) >= 100:
                break
                
            # 1. Название (обязательно)
            name_col = _find_column(original_columns, mappings["name"])
            if not name_col or pd.isna(row[name_col]):
                continue # Пропускаем строки без названия
            
            name = str(row[name_col]).strip()
            
            # 2. Цена
            price_col = _find_column(original_columns, mappings["price"])
            price = 0.0
            if price_col and not pd.isna(row[price_col]):
                # Очищаем цену от пробелов и символов валюты
                price_str = str(row[price_col]).replace(' ', '').replace('₽', '').replace('руб', '')
                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0
            
            # 3. Артикул (SKU)
            sku_col = _find_column(original_columns, mappings["sku"])
            sku = f"IMPORTED-{index}"
            if sku_col and not pd.isna(row[sku_col]):
                sku = str(row[sku_col]).strip()
            
            # 4. Описание
            desc_col = _find_column(original_columns, mappings["description"])
            description = ""
            if desc_col and not pd.isna(row[desc_col]):
                description = str(row[desc_col]).strip()[:500]
            
            # 5. Фото (может быть несколько через запятую)
            photo_col = _find_column(original_columns, mappings["photos"])
            photos = []
            if photo_col and not pd.isna(row[photo_col]):
                photo_str = str(row[photo_col]).strip()
                # Разделяем по запятой или точке с запятой, если несколько ссылок
                photos = [p.strip() for p in photo_str.replace(';', ',').split(',') if p.strip().startswith('http')]
            
            products.append({
                "name": name,
                "price": price,
                "sku": sku,
                "description": description,
                "photos": photos[:5], # Максимум 5 фото
                "category": "Импорт из файла" # По умолчанию, пользователь сможет поменять потом
            })
            
        logger.info(f"✅ Распарсено {len(products)} товаров из {file_type.upper()} ({platform})")
        return products
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга файла: {e}")
        raise ValueError(f"Не удалось прочитать файл. Убедитесь, что это корректный Excel или CSV. Ошибка: {e}")