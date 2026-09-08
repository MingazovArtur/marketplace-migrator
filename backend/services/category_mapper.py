import json
from pathlib import Path
from typing import Dict, Optional, List

class CategoryMapper:
    """Маппинг категорий между маркетплейсами на основе данных из API"""
    
    def __init__(self):
        self.data_file = Path(__file__).parent.parent / "data" / "marketplace_categories.json"
        self.data = self._load_data()
        
        # Индексы для быстрого поиска
        self._ozon_by_name = self._build_name_index(self.data.get("ozon_categories", {}))
        self._wb_by_name = self._build_name_index(self.data.get("wildberries_subjects", {}))
    
    def _load_data(self) -> Dict:
        """Загружает справочник категорий"""
        if self.data_file.exists():
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"ozon_categories": {}, "wildberries_subjects": {}, "mapping": {}}
    
    def _build_name_index(self, categories: Dict) -> Dict:
        """Строит индекс по названиям для быстрого поиска"""
        index = {}
        for cat_id, cat_data in categories.items():
            name = cat_data.get("name", "").lower()
            index[name] = cat_id
        return index
    
    def get_ozon_category(self, category_id: str) -> Optional[Dict]:
        """Получает категорию Ozon по ID"""
        return self.data.get("ozon_categories", {}).get(str(category_id))
    
    def get_wildberries_subject(self, subject_id: str) -> Optional[Dict]:
        """Получает subject Wildberries по ID"""
        return self.data.get("wildberries_subjects", {}).get(str(subject_id))
    
    def map_ozon_to_wildberries(self, ozon_category_id: str) -> Dict:
        """
        Преобразует категорию Ozon в subject Wildberries
        Возвращает: {"id": 1, "name": "Товары для дома"}
        """
        mapping = self.data.get("mapping", {}).get("ozon_to_wildberries", {})
        wb_id = mapping.get(str(ozon_category_id), "1")  # Дефолт
        
        return self.get_wildberries_subject(wb_id) or {"id": 1, "name": "Товары для дома"}
    
    def find_ozon_category_by_name(self, category_name: str) -> Optional[str]:
        """Ищет категорию Ozon по названию (точное или частичное совпадение)"""
        if not category_name:
            return None
        
        name_lower = category_name.lower()
        
        # Точное совпадение
        if name_lower in self._ozon_by_name:
            return self._ozon_by_name[name_lower]
        
        # Частичное совпадение
        for full_name, cat_id in self._ozon_by_name.items():
            if full_name in name_lower or name_lower in full_name:
                return cat_id
        
        return None
    
    def auto_map_by_text(self, source_text: str, target_marketplace: str) -> Dict:
        """
        Автоматический маппинг по тексту (когда нет ID)
        Использует ключевые слова
        """
        source_lower = source_text.lower()
        
        if target_marketplace == "wildberries":
            rules = [
                (["уборка", "швабра", "ведро", "поломоеч", "тряпк"], "1", "Товары для дома"),
                (["посуда", "миск", "салатник", "тарелк", "кружк"], "2", "Посуда"),
                (["электрон", "аудио", "видео", "наушник", "телефон", "ноутбук"], "3", "Электроника"),
                (["одежд", "футболк", "рубашк", "брюк", "плать"], "4", "Одежда"),
                (["книг", "журнал", "блокнот"], "5", "Книги"),
                (["игрушк", "детск", "малыш"], "6", "Детские товары"),
                (["красот", "здоров", "косметик"], "7", "Красота и здоровье"),
                (["спорт", "фитнес", "тренажёр"], "8", "Спорт и отдых"),
                (["продукт", "еда", "напитк", "чай"], "9", "Продукты питания"),
                (["животн", "зоо", "корм"], "10", "Зоотовары"),
            ]
            
            for keywords, wb_id, wb_name in rules:
                if any(kw in source_lower for kw in keywords):
                    return {"id": int(wb_id), "name": wb_name}
            
            return {"id": 1, "name": "Товары для дома"}  # Дефолт
        
        return {"id": 1, "name": "Общая категория"}
    
    def get_all_wildberries_subjects(self) -> List[Dict]:
        """Возвращает все категории WB (для выпадающего списка в UI)"""
        return list(self.data.get("wildberries_subjects", {}).values())
    
    def get_all_ozon_categories(self) -> List[Dict]:
        """Возвращает все категории Ozon"""
        return list(self.data.get("ozon_categories", {}).values())