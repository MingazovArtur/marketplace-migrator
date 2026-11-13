import json
from pathlib import Path


def _stem_ru(word: str) -> str:
    """Простой стемминг русских окончаний для сопоставления единственного/множественного числа."""
    w = word.lower().strip()
    if len(w) <= 3:
        return w
    for suffix in ("ами", "ями", "ев", "ов", "ей", "ам", "ям", "ах", "ях", "ую", "юю", "ые", "ие", "ой", "ий", "ый"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    for suffix in ("а", "я", "ы", "и", "е", "о", "у", "ю", "ь"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


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
        raw_tokens = re.findall(r"[a-zа-яё0-9]+", text_low)
        tokens = set(raw_tokens)
        stemmed_tokens = {_stem_ru(t) for t in raw_tokens if len(t) >= 3}

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
            parent_part = low.split("/")[0].strip()
            score = 0

            if type_part and type_part in text_low:
                score += 120 + len(type_part)
            else:
                # Проверяем совпадение по основе слова (например, «футболка» <-> «футболки»)
                type_words = [w for w in re.findall(r"[a-zа-яё0-9]+", type_part) if len(w) >= 3]
                type_stems = {_stem_ru(w) for w in type_words}
                common_stems = type_stems & stemmed_tokens
                if common_stems:
                    score += 100 + 15 * len(common_stems)

            if parent_part and parent_part in text_low:
                score += 50
            else:
                parent_stems = {
                    _stem_ru(w)
                    for w in re.findall(r"[a-zа-яё0-9]+", parent_part)
                    if len(w) >= 3
                }
                if parent_stems & stemmed_tokens:
                    score += 30

            name_tokens = set(re.findall(r"[a-zа-яё0-9]+", low))
            score += 10 * len(tokens & name_tokens)

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
        source_lower = (source_text or "").lower()

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

        # === МАППИНГ НА ЯНДЕКС МАРКЕТ / МЕГАМАРКЕТ / МАГНИТ МАРКЕТ / ALIEXPRESS ===
        if target_platform in ("yandex", "megamarket", "magnit", "aliexpress"):
            rules = [
                (["уборка", "швабра", "ведро"], "90636", "Товары для дома"),
                (["посуда", "миск", "салатник", "кружк", "тарелк"], "90634", "Посуда"),
                (["электрон", "аудио", "наушник", "смартфон", "телефон"], "90630", "Электроника"),
                (
                    ["одежд", "футболк", "брюк", "плать", "куртк", "худи", "свитер"],
                    "90632",
                    "Одежда",
                ),
                (["кроссовк", "кеды", "обув", "ботинк"], "90640", "Обувь"),
                (["книг", "журнал"], "90638", "Книги"),
                (["игрушк", "детск"], "90633", "Детские товары"),
                (["красот", "косметик", "парфюм"], "90631", "Красота и здоровье"),
                (["спорт", "фитнес"], "90635", "Спорт и отдых"),
                (["продукт", "еда", "чай", "кофе"], "90637", "Продукты питания"),
                (["животн", "зоо", "корм"], "90639", "Зоотовары"),
                (["светильник", "лампа"], "90636", "Товары для дома"),
            ]
            for keywords, y_id, y_name in rules:
                if any(kw in source_lower for kw in keywords):
                    return {"id": y_id, "name": y_name}
            return {"id": "90636", "name": "Товары для дома"}

        # === МАППИНГ НА ХОЛОДИЛЬНИК.РУ ===
        if target_platform == "holodilnik":
            rules = [
                (
                    ["холодильник", "морозильн", "плит", "стиральн", "посудомоечн"],
                    "HL-1",
                    "Крупная бытовая техника",
                ),
                (
                    [
                        "чайник",
                        "блендер",
                        "миксер",
                        "кофемашин",
                        "микроволнов",
                        "пылесос",
                        "утюг",
                    ],
                    "HL-2",
                    "Мелкая бытовая техника",
                ),
                (["телевизор", "аудио", "наушник", "колонк"], "HL-3", "ТВ и Аудио"),
                (
                    ["смартфон", "телефон", "ноутбук", "планшет", "компьютер"],
                    "HL-4",
                    "Смартфоны и гаджеты",
                ),
                (
                    ["кондиционер", "обогреватель", "вентилятор", "водонагреватель"],
                    "HL-5",
                    "Климатическая техника",
                ),
                (
                    ["посуда", "сковород", "кастрюл", "миск", "нож"],
                    "HL-6",
                    "Посуда и кухонные аксессуары",
                ),
            ]
            for keywords, h_id, h_name in rules:
                if any(kw in source_lower for kw in keywords):
                    return {"id": h_id, "name": h_name}
            return {"id": "HL-0", "name": "Бытовая техника и электроника"}

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
