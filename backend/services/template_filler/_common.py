"""Общие константы и чистые хелперы заполнителя эталонов (без I/O)."""

import re

VAT_LABELS = {"none": "Не облагается", "22": "22", "10": "10", "7": "7", "5": "5"}

BRAND_SYNONYMS = ["бренд", "брендводеждеиобуви", "брендодеждыиобуви", "производитель", "brand"]
MODEL_SYNONYMS = [
    "объединитьнаоднойкарточке",
    "названиемодели",
    "названиемоделидляобъединенияводнукарточку",
    "модель",
    "модельsellerspuid",
    "sellerspuid",
]
MARKING_SYNONYMS = ["нуженкодмаркировки", "кодмаркировки", "маркировка"]

UNIVERSAL_NAMES = {
    "универсальный",
    "универсальный (все категории)",
    "общий",
    "все категории",
    "default",
    "all",
}


def _norm(s: str) -> str:
    """Нормализация имени колонки/атрибута: только буквы+цифры, нижний регистр."""
    return re.sub(r"[^a-zа-я0-9]", "", (s or "").lower())


def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Zа-яА-Я]+", "_", name).strip("_")[:80] or "template"


def _normalize_multi(value: str) -> str:
    """Формат множественного выбора: «a;b» без лишних пробелов."""
    parts = re.split(r"[;,]", value or "")
    return ";".join(p.strip() for p in parts if p.strip())


def _strip_html(text: str) -> str:
    """Очищает описание от HTML-тегов (<p>, <br> и т.д.)."""
    if not text:
        return ""
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", str(text))
    cleaned = re.sub(r"(?i)</p>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">")):
        cleaned = cleaned.replace(ent, ch)
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def _generate_ean13(product: dict, prefix: str = "460") -> str:
    """
    Генерирует валидный 13-значный штрихкод GTIN / EAN-13 по стандарту GS1.
    Префикс 460 подходит для всех российских маркетплейсов (включая Мегамаркет,
    который отклоняет штрихкоды, начинающиеся с 2).
    """
    pid = int(product.get("id") or 1)
    base12 = f"{prefix}{pid:09d}"[:12]
    odd_sum = sum(int(base12[i]) for i in range(0, 12, 2))
    even_sum = sum(int(base12[i]) for i in range(1, 12, 2))
    check_digit = (10 - ((odd_sum + even_sum * 3) % 10)) % 10
    return f"{base12}{check_digit}"


def _format_comma_decimal(val: float | int | None) -> str | None:
    """Форматирует число с запятой и максимум 2 знаками после запятой (правило Мегамаркета)."""
    if val is None:
        return None
    try:
        num = round(float(val), 2)
        if num <= 0:
            return None
        s = f"{num:.2f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")
    except (TypeError, ValueError):
        return None


def _guess_category(product: dict) -> str:
    """Возвращает чистое название категории без значения «Не указана»."""
    for field in ("mapped_category", "category"):
        raw = (product.get(field) or "").strip()
        if raw and raw.lower() not in ("не указана", "без категории", "не маппировалось", "—"):
            parts = [p.strip() for p in re.split(r"[/\\>]", raw) if p.strip()]
            return parts[-1] if parts else raw

    name_low = (product.get("name") or "").lower()
    rules = [
        (["футболк", "майк", "лонгслив"], "Футболки и майки"),
        (["плать", "сарафан"], "Платья и сарафаны"),
        (["брюк", "джинс", "штаны"], "Брюки"),
        (["куртк", "пуховик", "ветровк", "пальто"], "Верхняя одежда"),
        (["толстовк", "худи", "свитшот", "джемпер", "свитер"], "Толстовки, свитшот и худи"),
        (["носки", "гольф", "колготк"], "Носки, чулки и колготки"),
        (["кроссовк", "кеды"], "Кроссовки и кеды"),
        (["смартфон", "телефон"], "Мобильные телефоны"),
        (["наушник", "гарнитур"], "Наушники и Bluetooth-гарнитуры"),
        (["швабр", "ведро", "щетк"], "Инвентарь для уборки"),
    ]
    for keywords, cat in rules:
        if any(k in name_low for k in keywords):
            return cat
    return "Товары для дома"
