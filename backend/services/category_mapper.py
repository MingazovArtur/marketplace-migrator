import json
from pathlib import Path


class CategoryMapper:
    """Универсальный маппинг категорий между любыми маркетплейсами"""

    def auto_map_to_spec(self, text: str, platform: str):
        """
        Ищет ТОЧНОЕ имя спека («Родитель / Тип») по тексту товара/категории.
        Возвращает category_name из platform_category_specs или None.
        """
        import re

        from database.models import PlatformCategorySpec
        from database.session import SessionLocal

        if not text:
            return None
        text_low = str(text).lower().strip()
        tokens = set(re.findall(r"[a-zа-яё0-9]+", text_low))

        db = SessionLocal()
        try:
            names = [
                n
                for (n,) in db.query(PlatformCategorySpec.category_name)
                .filter(PlatformCategorySpec.platform == platform)
                .all()
            ]
        finally:
            db.close()

        best_name, best_score = None, 0
        for name in names:
            low = name.lower()
            if low == text_low:
                return name  # точное совпадение
            type_part = low.split("/")[-1].strip()  # «футболка» из «Одежда / Футболка»
            score = 0
            if type_part and type_part in text_low:
                score += 100 + len(type_part)
            parent_part = low.split("/")[0].strip()
            if parent_part and parent_part in text_low:
                score += 50
            score += 10 * len(tokens & set(re.findall(r"[a-zа-яё0-9]+", low)))
            if score > best_score:
                best_name, best_score = name, score

        return best_name if best_score >= 100 else None  # порог: совпал ТИП товара

    def __init__(self):
        self.data_file = Path(__file__).parent.parent / "data" / "marketplace_categories.json"
        self.data = self._load_data()

        self._ozon_by_name = self._build_name_index(self.data.get("ozon_categories", {}))
        self._wb_by_name = self._build_name_index(self.data.get("wildberries_subjects", {}))
        self._yandex_by_name = self._build_name_index(self.data.get("yandex_categories", {}))

    def _load_data(self) -> dict:
        if self.data_file.exists():
            with open(self.data_file, encoding="utf-8") as f:
                return json.load(f)
        return {
            "ozon_categories": {},
            "wildberries_subjects": {},
            "yandex_categories": {},
            "mapping": {},
        }

    def _build_name_index(self, categories: dict) -> dict:
        index = {}
        for cat_id, cat_data in categories.items():
            name = cat_data.get("name", "").lower()
            index[name] = cat_id
        return index

    def auto_map_by_text(self, source_text: str, target_platform: str) -> dict:
        """Универсальный маппинг по тексту для любой целевой платформы"""
        source_lower = source_text.lower()

        # === МАППИНГ НА WILDBERRIES ===
        if target_platform == "wildberries":
            rules = [
                (["уборка", "швабра", "ведро", "поломоеч", "тряпк"], "1", "Товары для дома"),
                (["посуда", "миск", "салатник", "тарелк", "кружк"], "2", "Посуда"),
                (
                    ["электрон", "аудио", "видео", "наушник", "телефон", "ноутбук"],
                    "3",
                    "Электроника",
                ),
                (["одежд", "футболк", "рубашк", "брюк", "плать"], "4", "Одежда"),
                (["книг", "журнал", "блокнот"], "5", "Книги"),
                (["игрушк", "детск", "малыш"], "6", "Детские товары"),
                (["красот", "здоров", "косметик"], "7", "Красота и здоровье"),
                (["спорт", "фитнес", "тренажёр"], "8", "Спорт и отдых"),
                (["продукт", "еда", "напитк", "чай"], "9", "Продукты питания"),
                (["животн", "зоо", "корм"], "10", "Зоотовары"),
                (["чай", "кофе", "напит"], "9", "Продукты питания"),
                (["светильник", "лампа", "освещен"], "1", "Товары для дома"),
            ]
            for keywords, wb_id, wb_name in rules:
                if any(kw in source_lower for kw in keywords):
                    return {"id": int(wb_id), "name": wb_name}
            return {"id": 1, "name": "Товары для дома"}

        # === МАППИНГ НА ЯНДЕКС МАРКЕТ ===
        if target_platform == "yandex":
            rules = [
                (["уборка", "швабра", "ведро"], "90636", "Товары для дома"),
                (["посуда", "миск", "салатник"], "90634", "Посуда"),
                (["электрон", "аудио", "наушник"], "90630", "Электроника"),
                (["одежд", "футболк"], "90632", "Одежда"),
                (["книг", "журнал"], "90638", "Книги"),
                (["игрушк", "детск"], "90633", "Детские товары"),
                (["красот", "косметик"], "90631", "Красота и здоровье"),
                (["спорт", "фитнес"], "90635", "Спорт и отдых"),
                (["продукт", "еда", "чай", "кофе"], "90637", "Продукты питания"),
                (["животн", "зоо"], "90639", "Зоотовары"),
                (["светильник", "лампа"], "90636", "Товары для дома"),
            ]
            for keywords, y_id, y_name in rules:
                if any(kw in source_lower for kw in keywords):
                    return {"id": y_id, "name": y_name}
            return {"id": "90636", "name": "Товары для дома"}

        # === МАППИНГ НА OZON ===
        if target_platform == "ozon":
            rules = [
                (["уборка", "швабра", "ведро"], "101", "Уборка"),
                (["посуда", "миск"], "201", "Миски и салатники"),
                (["электрон", "аудио", "наушник"], "301", "Аудиотехника"),
                (["одежд", "футболк"], "401", "Мужская одежда"),
                (["книг"], "501", "Программирование"),
            ]
            for keywords, o_id, o_name in rules:
                if any(kw in source_lower for kw in keywords):
                    return {"id": o_id, "name": o_name}
            return {"id": "1", "name": "Дом и сад"}

        return {"id": "1", "name": "Общая категория"}

    def get_all_categories(self, platform: str) -> list[dict]:
        """Возвращает все категории для указанной платформы"""
        key_map = {
            "ozon": "ozon_categories",
            "wildberries": "wildberries_subjects",
            "yandex": "yandex_categories",
        }
        key = key_map.get(platform, "ozon_categories")
        return list(self.data.get(key, {}).values())
