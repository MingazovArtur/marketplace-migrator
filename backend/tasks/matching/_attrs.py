"""Конфигурация канонических атрибутов XLS-шаблона Ozon и их авто-дозаполнение.

Вынесено без изменений из монолита tasks/matching.py (Р20): CANON_ATTRS /
TNVED_NAMES и _ensure_canonical_attributes — добавление обязательных
атрибутов шаблона (бренд, модель, тип, маркировка, ТН ВЭД) с учётом
дефолтов пользователя и справочников значений спека.
"""

import logging

from services import defaults_service
from tasks.matching._cache import _load_spec_for_category
from tasks.matching._text import _norm_name

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация канонических атрибутов XLS-шаблона Ozon
# ---------------------------------------------------------------------------
CANON_ATTRS = {
    "brand": {
        "names": ["бренд", "брендводеждеиобуви", "брендодеждыиобуви"],
        "fallback": "NoName",
        "dict_pref": "нет бренда",
    },
    "model": {
        "names": [
            "названиемодели",
            "названиемоделидляобъединенияводнукарточку",
            "объединитьнаоднойкарточке",
            "объединитьводнукарточку",
            "модель",
        ],
        "fallback": None,
        "dict_pref": None,
    },
    "type": {
        "names": ["тип"],
        "fallback": "Футболка",
        "dict_pref": None,
    },
    "marking": {
        "names": ["нуженкодмаркировки", "кодмаркировки", "маркировка"],
        "fallback": "Нет",
        "dict_pref": "нет",
    },
}

TNVED_NAMES = ["тнвэдкодыеаэс", "тнвэд", "кодытнвэд"]


def _ensure_canonical_attributes(
    product_id: int,
    target_platform: str,
    target_category_name: str,
    product_name: str,
    okpd_code: str = None,
    user_id: int = None,
):
    if target_platform != "ozon" or not target_category_name:
        return

    spec = _load_spec_for_category(target_platform, target_category_name)
    if not spec or not isinstance(spec, dict):
        return

    defaults = (
        defaults_service.get_merged_defaults(user_id, target_category_name) if user_id else {}
    )
    spec_attrs = {
        _norm_name(a.get("name")): a for a in (spec.get("attributes") or []) if a.get("name")
    }
    if not spec_attrs:
        return

    derived_type = defaults_service.derive_type_value(target_category_name, spec)

    from database.models import ProductAttribute
    from database.session import SessionLocal

    db = SessionLocal()
    try:
        existing = {
            _norm_name(a.name)
            for a in db.query(ProductAttribute)
            .filter(ProductAttribute.product_id == product_id)
            .all()
        }
        added = 0
        for canon, cfg in CANON_ATTRS.items():
            keys = [n for n in cfg["names"] if n in spec_attrs and n not in existing]
            if not keys:
                continue

            first_attr = spec_attrs[keys[0]]
            values = first_attr.get("values") or []

            if canon == "model":
                value = (product_name or "").strip()[:50] or "Модель"
            elif canon == "type" and derived_type:
                value = derived_type
            elif canon == "brand":
                pref = (defaults.get("brand") or "").strip().lower()
                value = (
                    next((v for v in values if pref and pref in str(v).lower()), None)
                    or next((v for v in values if "нет бренда" in str(v).lower()), None)
                    or (values[0] if values else cfg["fallback"])
                )
            elif canon == "marking":
                value = defaults.get("marking") or next(
                    (v for v in values if str(v).lower() == "нет"), "Нет"
                )
            elif cfg.get("dict_pref") and values:
                value = next((v for v in values if cfg["dict_pref"] in str(v).lower()), values[0])
            elif values:
                value = values[0]
            else:
                value = cfg.get("fallback")
            if value is None:
                continue

            for key in keys:
                db.add(
                    ProductAttribute(
                        product_id=product_id,
                        name=spec_attrs[key].get("name"),
                        value=str(value),
                        sort_order=0,
                    )
                )
                existing.add(key)
                added += 1

        # ТН ВЭД из карточки или дефолтов
        okpd = okpd_code or defaults.get("okpd_code")
        tnved_key = next((n for n in TNVED_NAMES if n in spec_attrs and n not in existing), None)
        if okpd and tnved_key:
            db.add(
                ProductAttribute(
                    product_id=product_id,
                    name=spec_attrs[tnved_key].get("name"),
                    value=str(okpd),
                    sort_order=0,
                )
            )
            added += 1

        db.commit()
        if added:
            logger.info(
                f"🧩 Товар {product_id}: авто-добавлено {added} обязательных атрибутов шаблона"
            )
    except Exception as e:
        db.rollback()
        logger.warning(f"Авто-атрибуты для товара {product_id} не записаны: {e}")
    finally:
        db.close()
