"""
Хранилище и заполнение ЭТАЛОННЫХ шаблонов Ozon.

Пользователь скачивает XLSX-шаблон в кабинете Ozon для нужной категории и
загружает его в систему. Мы храним файл и при выгрузке ОТКРЫВАЕМ ЕГО КАК КАРКАС:
строки 1–4 (группы, заголовки, маркеры, подсказки), стили, ширины колонок,
data validation, скрытые листы-словари и доп. листы («Озон.Видео» и т.д.)
остаются нетронутыми — мы лишь дописываем строки товаров с 5-й строки,
раскладывая значения по колонкам через имена заголовков строки 2.

Результат гарантированно распознаётся кабинетом Ozon, т.к. это ИХ файл.
"""
import io
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path("/app/templates/ozon")
INDEX_PATH = TEMPLATES_DIR / "index.json"
DATA_START_ROW = 5

VAT_LABELS = {"none": "Не облагается", "22": "22", "10": "10", "7": "7", "5": "5"}

BRAND_SYNONYMS = ["бренд", "брендводеждеиобуви", "брендодеждыиобуви"]
MODEL_SYNONYMS = [
    "объединитьнаоднойкарточке", "названиемодели",
    "названиемоделидляобъединенияводнукарточку", "модель",
]
MARKING_SYNONYMS = ["нуженкодмаркировки", "кодмаркировки", "маркировка"]


# ==================== Служебные ====================

def _norm(s: str) -> str:
    """Нормализация имени колонки/атрибута: только буквы+цифры, нижний регистр."""
    return re.sub(r"[^a-zа-я0-9]", "", (s or "").lower())


def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Zа-яА-Я]+", "_", name).strip("_")[:80] or "category"


def _normalize_multi(value: str) -> str:
    """Ozon-формат множественного выбора: «a;b» без пробелов."""
    parts = re.split(r"[;,]", value or "")
    return ";".join(p.strip() for p in parts if p.strip())


def _load_index() -> Dict[str, str]:
    if INDEX_PATH.exists():
        try:
            return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_index(index: Dict[str, str]) -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


# ==================== Публичный API хранилища ====================

def has_official_template(category_name: str) -> bool:
    idx = _load_index()
    fname = idx.get(category_name)
    return bool(fname) and (TEMPLATES_DIR / fname).exists()


def list_official_templates() -> List[str]:
    idx = _load_index()
    return sorted(cat for cat, fname in idx.items() if (TEMPLATES_DIR / fname).exists())


def save_official_template(category_name: str, data: bytes) -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    idx = _load_index()
    fname = f"{_slug(category_name)}.xlsx"
    # Защита от коллизий slug между разными категориями
    owner = next((cat for cat, f in idx.items() if f == fname), None)
    if owner and owner != category_name:
        fname = f"{_slug(category_name)}_{abs(hash(category_name)) % 10000}.xlsx"
    (TEMPLATES_DIR / fname).write_bytes(data)
    idx[category_name] = fname
    _save_index(idx)
    logger.info(f"💾 Эталонный шаблон Ozon сохранён: категория '{category_name}' → {fname}")


def delete_official_template(category_name: str) -> bool:
    idx = _load_index()
    fname = idx.pop(category_name, None)
    _save_index(idx)
    if fname and (TEMPLATES_DIR / fname).exists():
        (TEMPLATES_DIR / fname).unlink()
        return True
    return False


def validate_template_bytes(data: bytes) -> Optional[str]:
    """
    Быстрая проверка, что файл похож на шаблон Ozon.
    Возвращает текст ошибки или None, если всё хорошо.
    """
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True)
    except Exception as e:
        return f"Файл не читается как XLSX: {e}"
    try:
        ws = wb["Шаблон"] if "Шаблон" in wb.sheetnames else wb.active
        header_row = _find_header_row(ws)
        if header_row is None:
            return "В листе «Шаблон» не найдена строка заголовков с колонкой «Артикул»"
        headers = {_norm(str(c.value).rstrip("*")) for c in ws[header_row] if c.value}
        if "артикул" not in headers or "ндс" not in headers:
            return "Структура не похожа на шаблон Ozon (нет колонок «Артикул» / «НДС, %»)"
        return None
    finally:
        wb.close()


def _find_header_row(ws) -> Optional[int]:
    """Строка заголовков: обычно 2-я; ищем «Артикул» на случай сдвига."""
    for row in range(1, 6):
        for cell in ws[row]:
            if cell.value and _norm(str(cell.value).rstrip("*")) == "артикул":
                return row
    return None


# ==================== Значения строки товара ====================

def _row_values(product: dict, row_num: int, enum_fix: Dict[str, Dict[str, str]]) -> Dict[str, object]:
    """Значения строки товара. Ключи — нормализованные имена колонок эталона."""
    photos = product.get("photos") or []
    attr_map = {_norm(a.get("name")): a.get("value")
                for a in (product.get("attributes") or []) if a.get("name")}

    values: Dict[str, object] = {
        "№": row_num,
        "артикул": product.get("_article") or product.get("sku")
                   or product.get("external_id") or f"ID{product.get('id')}",
        "названиетовара": product.get("name"),
        "предельнаяценабезакцийруб": product.get("price"),
        "зачёркнутаяценаруб": product.get("strike_price"),
        "ндс": VAT_LABELS.get(str(product.get("vat_rate") or ""), product.get("vat_rate")),
        "штрихкодсерийныйномерean": _normalize_multi(product.get("barcode") or "") or None,
        "тнвэдкодыеаэс": product.get("okpd_code"),
        "весвупаковкег": product.get("package_weight_grams"),
        "ширинаупаковкимм": product.get("package_width_mm"),
        "высотаупаковкимм": product.get("package_height_mm"),
        "длинаупаковкимм": product.get("package_length_mm"),
        "ссылканаглавноефото": photos[0] if photos else None,
        "ссылкинадполнительныефото": " ".join(photos[1:15]) if len(photos) > 1 else None,
    }

    # Атрибуты товара — по нормализованному имени колонки
    for key, val in attr_map.items():
        if val not in (None, ""):
            values.setdefault(key, val)

    # Фолбэки-синонимы канонических колонок
    if not any(values.get(b) for b in BRAND_SYNONYMS):
        for b in BRAND_SYNONYMS:
            if attr_map.get(b):
                values[b] = attr_map[b]
                break
    if not any(values.get(m) for m in MODEL_SYNONYMS):
        values[MODEL_SYNONYMS[0]] = product.get("name")     # модель = название товара
    if not any(values.get(m) for m in MARKING_SYNONYMS):
        values[MARKING_SYNONYMS[0]] = "Нет"
    if not values.get("количествовупаковке") and not values.get("количествовупаковкешт"):
        if product.get("units_per_item"):
            values["количествовупаковке"] = product.get("units_per_item")

    # Приведение значений к регистру словаря площадки + формат «a;b»
    for key, val in list(values.items()):
        if val in (None, ""):
            continue
        s = str(val)
        if ";" in s or "," in s:
            s = _normalize_multi(s)
        fix = enum_fix.get(key)
        if fix:
            s = fix.get(s.strip().lower(), s)
        values[key] = s
    return values


def _build_enum_fix(spec: Optional[dict]) -> Dict[str, Dict[str, str]]:
    """Индекс нормализованных словарных значений для исправления регистра."""
    fix: Dict[str, Dict[str, str]] = {}
    for a in (spec or {}).get("attributes") or []:
        vals = a.get("values") or []
        if vals:
            fix[_norm(a.get("name"))] = {str(v).strip().lower(): str(v) for v in vals}
    return fix


# ==================== Заполнение эталона ====================

def fill_official_template(category_name: str, products: list, spec: Optional[dict] = None) -> bytes:
    """
    Открывает эталонный файл Ozon категории и дописывает товары с 5-й строки.
    Формат (строки 1–4, стили, списки, листы) остаётся нетронутым.
    """
    idx = _load_index()
    fname = idx.get(category_name)
    if not fname:
        raise ValueError(f"Эталонный шаблон для категории '{category_name}' не загружен")

    wb = load_workbook(io.BytesIO((TEMPLATES_DIR / fname).read_bytes()))
    ws = wb["Шаблон"] if "Шаблон" in wb.sheetnames else wb.active

    header_row = _find_header_row(ws) or 2
    headers: Dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        h = ws.cell(row=header_row, column=col).value
        if h:
            headers[_norm(str(h).rstrip("*").strip())] = col

    # ✅ Зачищаем примеры/старые данные ниже шапки (в скачанных файлах бывает тест-строка)
    if ws.max_row >= DATA_START_ROW:
        ws.delete_rows(DATA_START_ROW, ws.max_row - DATA_START_ROW + 1)

    # Уникализация артикулов (правило Ozon: дубли → _2, _3)
    seen: Dict[str, int] = {}
    for p in products:
        base = p.get("sku") or p.get("external_id") or f"ID{p.get('id')}"
        seen[base] = seen.get(base, 0) + 1
        p["_article"] = base if seen[base] == 1 else f"{base}_{seen[base]}"

    enum_fix = _build_enum_fix(spec)

    for i, product in enumerate(products, start=1):
        values = _row_values(product, i, enum_fix)
        r = DATA_START_ROW + i - 1
        for key, col in headers.items():
            val = values.get(key)
            if val in (None, ""):
                continue
            # Числовые колонки отдаём числами, а не строками
            if key in ("весвупаковкег", "ширинаупаковкимм", "высотаупаковкимм",
                       "длинаупаковкимм", "предельнаяценабезакцийруб", "зачёркнутаяценаруб"):
                try:
                    num = float(val)
                    val = int(num) if num == int(num) else num
                except (TypeError, ValueError):
                    pass
            ws.cell(row=r, column=col, value=val)

    buf = io.BytesIO()
    wb.save(buf)
    logger.info(f"✅ Эталон '{category_name}': заполнено строк товаров: {len(products)}")
    return buf.getvalue()