"""
Дефолты экспорта и массовое дозаполнение пропусков.

Иерархия: дефолты категории перекрывают глобальные дефолты пользователя.
Используется:
  - кнопкой «Заполнить пропуски» (POST /api/products/apply-defaults);
  - задачами миграции (tasks.py) для авто-заполнения логистики и атрибутов.

Правило безопасности: дефолты подставляются ТОЛЬКО в пустые/нулевые поля.
Уже заполненные пользователем значения никогда не перезаписываются.
"""
import logging
import re
from typing import Dict, Optional

from database.session import SessionLocal
from database.models import ExportDefault, Product

logger = logging.getLogger(__name__)

BASE_FIELDS = [
    "vat_rate", "okpd_code",
    "package_weight_grams", "package_width_mm", "package_height_mm", "package_length_mm",
]

# Поля, участвующие в слиянии дефолтов (база + бренд/маркировка + цена)
MERGE_FIELDS = BASE_FIELDS + ["brand", "marking", "price_default"]


def _norm(s: str) -> str:
    return re.sub(r"[^a-zа-я0-9]", "", (s or "").lower())


def _is_empty(v) -> bool:
    return v is None or v == "" or v == 0


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def get_merged_defaults(user_id: int, category_name: Optional[str] = None) -> Dict[str, object]:
    """Слияние: глобальные дефолты ← дефолты категории (категория важнее)."""
    db = SessionLocal()
    try:
        rows = [
            db.query(ExportDefault)
            .filter(ExportDefault.user_id == user_id, ExportDefault.category_name.is_(None))
            .first()
        ]
        if category_name:
            rows.append(
                db.query(ExportDefault)
                .filter(ExportDefault.user_id == user_id,
                        ExportDefault.category_name == category_name)
                .first()
            )
        merged: Dict[str, object] = {}
        for row in rows:
            if not row:
                continue
            for f in MERGE_FIELDS:
                v = getattr(row, f, None)
                if v in (None, ""):
                    continue
                if f == "price_default":
                    v = _to_float(v)          # Decimal(Numeric) → float
                    if v is None or v <= 0:
                        continue
                merged[f] = v
        return merged
    finally:
        db.close()


def compute_gaps(user_id: int, status: str = "all") -> Dict[str, object]:
    """Счётчик пропусков по полям — для баннера «Заполнить пропуски (N)»."""
    db = SessionLocal()
    try:
        q = db.query(Product).filter(Product.user_id == user_id)
        if status and status != "all":
            q = q.filter(Product.status == status)
        products = q.all()
        gaps = {f: 0 for f in BASE_FIELDS}
        gaps["price"] = 0
        gaps["main_photo"] = 0
        for p in products:
            for f in BASE_FIELDS:
                if _is_empty(getattr(p, f, None)):
                    gaps[f] += 1
            price = _to_float(p.price)
            if price is None or price <= 0:
                gaps["price"] += 1
            if not (p.photos or []):
                gaps["main_photo"] += 1
        return {"total": len(products), "gaps": gaps}
    finally:
        db.close()


def build_updates_for_product(product: Dict[str, object], user_id: int) -> Dict[str, object]:
    """
    Какие поля дозаполнить из дефолтов (только пустые/нулевые).
    Принимает dict с ключами: price, vat_rate, okpd_code, package_*, mapped_category, category.
    """
    category = product.get("mapped_category") or product.get("category")
    d = get_merged_defaults(user_id, category)
    updates: Dict[str, object] = {}

    # Базовые поля логистики
    for f in BASE_FIELDS:
        if _is_empty(product.get(f)) and not _is_empty(d.get(f)):
            updates[f] = d[f]

    # ✅ Цена по умолчанию — ТОЛЬКО если текущая цена пустая/нулевая/невалидная
    cur_price = _to_float(product.get("price"))
    if (cur_price is None or cur_price <= 0) and d.get("price_default"):
        updates["price"] = float(d["price_default"])

    return updates


def derive_type_value(category_name: str, spec: Optional[dict]) -> Optional[str]:
    """✅ Умный Тип: часть после «/» категории, сверенная со словарём спека по регистру."""
    type_part = (category_name or "").split("/")[-1].strip()
    if not type_part or not spec:
        return None
    low = type_part.lower()
    for a in spec.get("attributes") or []:
        if _norm(a.get("name")) != "тип":
            continue
        for v in a.get("values") or []:
            if str(v).strip().lower() == low:
                return str(v)
    return None