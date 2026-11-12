"""Хранилище эталонных шаблонов: index.json + файлы XLSX, мультиплатформенное,
с умным фолбэком поиска (точное совпадение → лист категории → универсальный → первый)."""

import io
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from services.template_filler._common import UNIVERSAL_NAMES, _slug
from services.template_filler._sheet_scan import _find_data_sheet, _find_header_row

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(os.getenv("OZON_TEMPLATES_DIR", "/app/templates/ozon"))
INDEX_PATH = TEMPLATES_DIR / "index.json"


def _make_key(platform: str, category_name: str) -> str:
    return f"{(platform or 'ozon').lower().strip()}::{(category_name or '').strip()}"


def _parse_key(raw_key: str, meta: dict) -> tuple[str, str]:
    if "::" in raw_key:
        pl, cat = raw_key.split("::", 1)
        return pl.lower().strip(), cat.strip()
    pl = (meta.get("platform") or "ozon").lower().strip()
    return pl, raw_key.strip()


def _load_index() -> dict[str, dict]:
    """Читает index.json с поддержкой мультиплатформенности и обратной совместимости."""
    if not INDEX_PATH.exists():
        return {}
    try:
        raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for k, val in (raw or {}).items():
        if isinstance(val, str):
            pl, cat = _parse_key(k, {})
            norm_key = _make_key(pl, cat)
            out[norm_key] = {
                "platform": pl,
                "category_name": cat,
                "file": val,
                "uploaded_at": None,
                "uploaded_by": None,
                "columns": None,
            }
        elif isinstance(val, dict) and val.get("file"):
            pl, cat = _parse_key(k, val)
            cat_name = val.get("category_name") or cat
            norm_key = _make_key(pl, cat_name)
            out[norm_key] = {
                "platform": pl,
                "category_name": cat_name,
                "file": val.get("file"),
                "uploaded_at": val.get("uploaded_at"),
                "uploaded_by": val.get("uploaded_by"),
                "columns": val.get("columns"),
            }
    return out


def _save_index(index: dict[str, dict]) -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _count_columns(data: bytes) -> int | None:
    """Число непустых колонок в строке заголовков шаблона."""
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True)
        try:
            ws = _find_data_sheet(wb)
            row = _find_header_row(ws) or 2
            return sum(1 for c in ws[row] if c.value not in (None, ""))
        finally:
            wb.close()
    except Exception:
        return None


# ==================== Поиск эталона с умным фолбэком ====================


def _resolve_template_meta(category_name: str | None, platform: str = "ozon") -> dict | None:
    """
    Ищет подходящий эталонный шаблон для площадки:
      1. Точное совпадение (platform, category_name).
      2. Совпадение по конечному типу категории («Одежда / Футболки» -> «Футболки»).
      3. Универсальный шаблон площадки («Универсальный», «Общий», «Все категории»).
      4. Фолбэк: первый доступный шаблон этой площадки.
    """
    pl = (platform or "ozon").lower().strip()
    cat = (category_name or "").strip()
    idx = _load_index()

    platform_templates: list[dict] = []
    for meta in idx.values():
        if meta.get("platform") == pl and (TEMPLATES_DIR / meta["file"]).exists():
            platform_templates.append(meta)

    if not platform_templates:
        return None

    if cat:
        for m in platform_templates:
            if m["category_name"].lower() == cat.lower():
                return m

        cat_leaf = cat.split("/")[-1].strip().lower()
        for m in platform_templates:
            m_leaf = m["category_name"].split("/")[-1].strip().lower()
            if cat_leaf and m_leaf == cat_leaf:
                return m

    for m in platform_templates:
        if m["category_name"].strip().lower() in UNIVERSAL_NAMES:
            return m

    return platform_templates[0]


# ==================== Публичный API хранилища ====================


def has_official_template(category_name: str = "", platform: str = "ozon") -> bool:
    return _resolve_template_meta(category_name, platform) is not None


def template_path(category_name: str = "", platform: str = "ozon") -> Path | None:
    meta = _resolve_template_meta(category_name, platform)
    if not meta:
        return None
    p = TEMPLATES_DIR / meta["file"]
    return p if p.exists() else None


def get_template_meta(category_name: str = "", platform: str = "ozon") -> dict | None:
    return _resolve_template_meta(category_name, platform)


def list_official_templates(platform: str | None = None) -> list[dict]:
    """Метаданные всех эталонов (опционально отфильтрованные по площадке)."""
    idx = _load_index()
    res = []
    pl_filter = platform.lower().strip() if platform else None
    for meta in idx.values():
        if pl_filter and meta.get("platform") != pl_filter:
            continue
        if (TEMPLATES_DIR / meta["file"]).exists():
            res.append(meta)
    return sorted(res, key=lambda x: (x.get("platform") or "ozon", x.get("category_name") or ""))


def list_template_names(platform: str | None = None) -> list[str]:
    return [t["category_name"] for t in list_official_templates(platform=platform)]


def read_template_bytes(category_name: str, platform: str = "ozon") -> bytes | None:
    idx = _load_index()
    exact = idx.get(_make_key(platform, category_name))
    if exact and (TEMPLATES_DIR / exact["file"]).exists():
        return (TEMPLATES_DIR / exact["file"]).read_bytes()
    p = template_path(category_name, platform=platform)
    return p.read_bytes() if p else None


def save_official_template(
    category_name: str,
    data: bytes,
    uploaded_by: str | None = None,
    platform: str = "ozon",
) -> dict:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    pl = (platform or "ozon").lower().strip()
    cat = (category_name or "").strip() or "Универсальный (все категории)"

    idx = _load_index()
    key = _make_key(pl, cat)
    fname = f"{pl}_{_slug(cat)}.xlsx"

    owner = next((k for k, m in idx.items() if m["file"] == fname), None)
    if owner and owner != key:
        fname = f"{pl}_{_slug(cat)}_{abs(hash(key)) % 10000}.xlsx"

    (TEMPLATES_DIR / fname).write_bytes(data)
    meta = {
        "platform": pl,
        "category_name": cat,
        "file": fname,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "uploaded_by": uploaded_by,
        "columns": _count_columns(data),
    }
    idx[key] = meta
    _save_index(idx)
    logger.info(
        f"💾 Эталон [{pl}] сохранён: '{cat}' → {fname} "
        f"(колонок: {meta['columns']}, загрузил: {uploaded_by})"
    )
    return meta


def delete_official_template(category_name: str, platform: str = "ozon") -> bool:
    idx = _load_index()
    key = _make_key(platform, category_name)
    meta = idx.pop(key, None)
    if not meta:
        for k in list(idx.keys()):
            if k.lower() == key.lower():
                meta = idx.pop(k)
                break
    _save_index(idx)
    if meta and (TEMPLATES_DIR / meta["file"]).exists():
        (TEMPLATES_DIR / meta["file"]).unlink()
        return True
    return False


def validate_template_bytes(data: bytes, platform: str = "ozon") -> str | None:
    """Проверяет, что загруженный файл является корректным XLSX-шаблоном площадки."""
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True)
    except Exception as e:
        return f"Файл не читается как XLSX: {e}"
    try:
        ws = _find_data_sheet(wb)
        header_row = _find_header_row(ws)
        if header_row is None:
            return (
                "В файле не найдена строка заголовков (ожидается колонка «Артикул», "
                "«Ваш SKU *», «Код товара продавца», «Модель (seller SPU ID)*» или «Наименование»)"
            )
        return None
    finally:
        wb.close()
