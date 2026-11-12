"""Сериализация Product в словарь API (P-1: Decimal → float)."""

from database.models import Product


class _SerializeMixin:
    """_to_dict — единый формат товара для JSON и openpyxl (Р14).

    Вызывается и как self._to_dict (методы репозитория), и напрямую
    через класс (`ProductRepository._to_dict` — tests/test_money_helpers.py).
    """

    # ---------- внутренний хелпер сериализации ----------
    @staticmethod
    def _to_dict(p: Product) -> dict | None:
        if p is None:
            return None
        return {
            # --- базовые поля ---
            "id": p.id,
            "name": p.name,
            "source": p.source,
            # P-1: Numeric-колонки отдают Decimal — наружу (JSON/openpyxl) отдаём float
            "price": float(p.price) if p.price is not None else None,
            "status": p.status,
            "description": p.description,
            "photos_count": p.photos_count,
            "category": p.category,
            "mapped_category": p.mapped_category,
            "error_message": p.error_message,
            "user_id": p.user_id,
            "sku": p.sku,
            "external_id": p.external_id,
            "brand": p.brand,
            "photos": p.photos or [],
            "sku_count": p.sku_count or 1,
            "stock": p.stock,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            # --- ✅ ЛОГИСТИКА И НАЛОГИ ---
            "barcode": p.barcode,
            "weight_grams": p.weight_grams,
            "package_weight_grams": p.package_weight_grams,
            "package_width_mm": p.package_width_mm,
            "package_height_mm": p.package_height_mm,
            "package_length_mm": p.package_length_mm,
            "vat_rate": p.vat_rate,
            "okpd_code": p.okpd_code,
            "units_per_item": p.units_per_item,
            # --- связи (загружаются через selectinload) ---
            "attributes": [
                {
                    "id": a.id,
                    "name": a.name,
                    "value": a.value,
                    "platform_attribute_id": a.platform_attribute_id,
                    "sort_order": a.sort_order,
                }
                for a in (p.attributes or [])
            ],
            "variants": [
                {
                    "id": v.id,
                    "sku": v.sku,
                    "size": v.size,
                    "color": v.color,
                    # P-1: Decimal -> float
                    "price": float(v.price) if v.price is not None else None,
                    "stock": v.stock,
                    "sort_order": v.sort_order,
                }
                for v in (p.variants or [])
            ],
        }
