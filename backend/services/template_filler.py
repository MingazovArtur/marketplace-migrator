"""
Хранилище и заполнение ЭТАЛОННЫХ шаблонов Ozon.

Пользователь скачивает XLSX-шаблон в кабинете Ozon для нужной категории и
загружает его в систему. Мы храним файл и при выгрузке ОТКРЫВАЕМ ЕГО КАК КАРКАС:
строки 1–4 (группы, заголовки, маркеры, подсказки), стили, ширины колонок,
data validation, скрытые листы-словари и доп. листы («Озон.Видео» и т.д.)
остаются нетронутыми — мы лишь дописываем строки товаров с 5-й строки,
раскладывая значения по колонкам через имена заголовков строки 2.

✅ ШАБЛОНЫ ОБЩИЕ ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ: хранятся в volume /app/templates/ozon,
   привязка только к имени категории (без user_id). uploaded_by — лишь аудит.

Формат index.json (v2):
{
  "Одежда / Футболка": {
    "file": "odezhda_futbolka.xlsx",
    "uploaded_at": "2026-09-28T10:00:00",
    "uploaded_by": "admin",
    "columns": 80
  },
  ...
}
Обратная совместимость v1 ({"категория": "file.xlsx"}) поддерживается при чтении.
"""

import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path("/app/templates/ozon")
INDEX_PATH = TEMPLATES_DIR / "index.json"
DATA_START_ROW = 5

VAT_LABELS = {"none": "Не облагается", "22": "22", "10": "10", "7": "7", "5": "5"}

BRAND_SYNONYMS = ["бренд", "брендводеждеиобуви", "брендодеждыиобуви"]
MODEL_SYNONYMS = [
    "объединитьнаоднойкарточке",
    "названиемодели",
    "названиемоделидляобъединенияводнукарточку",
    "модель",
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


def _load_index() -> dict[str, dict]:
    """Читает index.json с миграцией старого формата v1 → v2."""
    if not INDEX_PATH.exists():
        return {}
    try:
        raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for cat, val in (raw or {}).items():
        if isinstance(val, str):  # v1: просто имя файла
            out[cat] = {"file": val, "uploaded_at": None, "uploaded_by": None, "columns": None}
        elif isinstance(val, dict) and val.get("file"):
            out[cat] = {
                "file": val.get("file"),
                "uploaded_at": val.get("uploaded_at"),
                "uploaded_by": val.get("uploaded_by"),
                "columns": val.get("columns"),
            }
    return out


def _save_index(index: dict[str, dict]) -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_header_row(ws) -> int | None:
    """Строка заголовков: обычно 2-я; ищем «Артикул» на случай сдвига."""
    for row in range(1, 6):
        for cell in ws[row]:
            if cell.value and _norm(str(cell.value).rstrip("*")) == "артикул":
                return row
    return None


def _count_columns(data: bytes) -> int | None:
    """Число колонок шаблона (непустые заголовки строки 2) — для метаданных."""
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True)
        try:
            ws = wb["Шаблон"] if "Шаблон" in wb.sheetnames else wb.active
            row = _find_header_row(ws) or 2
            return sum(1 for c in ws[row] if c.value not in (None, ""))
        finally:
            wb.close()
    except Exception:
        return None


# ==================== Публичный API хранилища ====================


def has_official_template(category_name: str) -> bool:
    meta = _load_index().get(category_name)
    return bool(meta) and (TEMPLATES_DIR / meta["file"]).exists()


def template_path(category_name: str) -> Path | None:
    meta = _load_index().get(category_name)
    if not meta:
        return None
    p = TEMPLATES_DIR / meta["file"]
    return p if p.exists() else None


def get_template_meta(category_name: str) -> dict | None:
    meta = _load_index().get(category_name)
    if not meta or not (TEMPLATES_DIR / meta["file"]).exists():
        return None
    return {"category_name": category_name, **meta}


def list_official_templates() -> list[dict]:
    """✅ Метаданные всех эталонов (для страницы «Шаблоны площадок»)."""
    idx = _load_index()
    res = []
    for cat, meta in idx.items():
        if (TEMPLATES_DIR / meta["file"]).exists():
            res.append({"category_name": cat, **meta})
    return sorted(res, key=lambda x: x["category_name"])


def list_template_names() -> list[str]:
    """Имена категорий с эталонами (обратная совместимость со старым UI)."""
    return [t["category_name"] for t in list_official_templates()]


def read_template_bytes(category_name: str) -> bytes | None:
    p = template_path(category_name)
    return p.read_bytes() if p else None


def save_official_template(
    category_name: str, data: bytes, uploaded_by: str | None = None
) -> dict:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    idx = _load_index()
    fname = f"{_slug(category_name)}.xlsx"
    # Защита от коллизий slug между разными категориями
    owner = next((cat for cat, m in idx.items() if m["file"] == fname), None)
    if owner and owner != category_name:
        fname = f"{_slug(category_name)}_{abs(hash(category_name)) % 10000}.xlsx"
    (TEMPLATES_DIR / fname).write_bytes(data)
    meta = {
        "file": fname,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "uploaded_by": uploaded_by,
        "columns": _count_columns(data),
    }
    idx[category_name] = meta
    _save_index(idx)
    logger.info(
        f"💾 Эталон Ozon сохранён: '{category_name}' → {fname} "
        f"(колонок: {meta['columns']}, загрузил: {uploaded_by})"
    )
    return meta


def delete_official_template(category_name: str) -> bool:
    idx = _load_index()
    meta = idx.pop(category_name, None)
    _save_index(idx)
    if meta and (TEMPLATES_DIR / meta["file"]).exists():
        (TEMPLATES_DIR / meta["file"]).unlink()
        return True
    return False


def validate_template_bytes(data: bytes) -> str | None:
    """Быстрая проверка, что файл похож на шаблон Ozon. Возвращает ошибку или None."""
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


# ==================== Значения строки товара ====================


def _row_values(
    product: dict, row_num: int, enum_fix: dict[str, dict[str, str]]
) -> dict[str, object]:
    """Значения строки товара. Ключи — нормализованные имена колонок эталона."""
    photos = product.get("photos") or []
    attr_map = {
        _norm(a.get("name")): a.get("value")
        for a in (product.get("attributes") or [])
        if a.get("name")
    }

    values: dict[str, object] = {
        "№": row_num,
        "артикул": product.get("_article")
        or product.get("sku")
        or product.get("external_id")
        or f"ID{product.get('id')}",
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
        values[MODEL_SYNONYMS[0]] = product.get("name")  # модель = название товара
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


def _build_enum_fix(spec: dict | None) -> dict[str, dict[str, str]]:
    """Индекс нормализованных словарных значений для исправления регистра."""
    fix: dict[str, dict[str, str]] = {}
    for a in (spec or {}).get("attributes") or []:
        vals = a.get("values") or []
        if vals:
            fix[_norm(a.get("name"))] = {str(v).strip().lower(): str(v) for v in vals}
    return fix


# ==================== Заполнение эталона ====================


def fill_official_template(
    category_name: str, products: list, spec: dict | None = None
) -> bytes:
    """
    Открывает эталонный файл Ozon категории и дописывает товары с 5-й строки.
    Формат (строки 1–4, стили, списки, листы) остаётся нетронутым.
    """
    path = template_path(category_name)
    if not path:
        raise ValueError(f"Эталонный шаблон для категории '{category_name}' не загружен")

    wb = load_workbook(io.BytesIO(path.read_bytes()))
    ws = wb["Шаблон"] if "Шаблон" in wb.sheetnames else wb.active

    header_row = _find_header_row(ws) or 2
    headers: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        h = ws.cell(row=header_row, column=col).value
        if h:
            headers[_norm(str(h).rstrip("*").strip())] = col

    # ✅ Зачищаем примеры/старые данные ниже шапки
    if ws.max_row >= DATA_START_ROW:
        ws.delete_rows(DATA_START_ROW, ws.max_row - DATA_START_ROW + 1)

    # Уникализация артикулов (правило Ozon: дубли → _2, _3)
    seen: dict[str, int] = {}
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
            if key in (
                "весвупаковкег",
                "ширинаупаковкимм",
                "высотаупаковкимм",
                "длинаупаковкимм",
                "предельнаяценабезакцийруб",
                "зачёркнутаяценаруб",
            ):
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
