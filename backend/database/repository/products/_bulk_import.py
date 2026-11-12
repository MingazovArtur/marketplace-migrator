"""P-2: пакетный импорт распарсенных товаров (create/upsert) — одна сессия
на весь импорт, существующие для upsert выбираются одним запросом на чанк,
варианты/атрибуты вставляются пачкой, один commit на чанк (200 товаров).

Статические хелперы _variant_rows/_attr_rows вызываются и через класс
(`ProductRepository._variant_rows` — variant_repo/attr_repo), поэтому
остаются статическими методами миксина, доступными через наследование."""

from sqlalchemy import or_

from database.models import Product, ProductAttribute, ProductVariant
from database.session import SessionLocal


class _BulkImportMixin:
    """_import_payload / _variant_rows / _attr_rows / bulk_import (Р14)."""

    @staticmethod
    def _import_payload(p_data: dict, user_id: int, source_label: str):
        """Нормализация распарсенных данных файла в колонки Product."""
        okpd_val = p_data.get("okpd_code") or p_data.get("tn_ved") or p_data.get("okpd2") or None
        payload = {
            "user_id": user_id,
            "name": p_data.get("name"),
            "source": source_label,
            "price": p_data.get("price", 0),
            "status": "pending",
            "description": p_data.get("description", ""),
            "photos_count": len(p_data.get("photos", [])),
            "category": p_data.get("category", "Не указана"),
            "sku": p_data.get("sku"),
            "external_id": p_data.get("external_id"),
            "brand": p_data.get("brand"),
            "photos": p_data.get("photos", []),
            "sku_count": p_data.get("sku_count", 1),
            "barcode": p_data.get("barcode") or None,
            "weight_grams": p_data.get("weight_grams"),
            "package_weight_grams": p_data.get("package_weight_grams"),
            "package_width_mm": p_data.get("package_width_mm"),
            "package_height_mm": p_data.get("package_height_mm"),
            "package_length_mm": p_data.get("package_length_mm"),
            "vat_rate": p_data.get("vat_rate") or None,
            "okpd_code": okpd_val,
            "units_per_item": p_data.get("units_per_item", 1),
        }
        return payload, (p_data.get("variants") or []), (p_data.get("attributes") or [])

    @staticmethod
    def _variant_rows(product_id: int, variants: list) -> list:
        """Строки ProductVariant из данных парсера (пустые SKU пропускаются)."""
        rows = []
        for idx, v in enumerate(variants):
            sku = str(v.get("sku") or "").strip()
            if not sku:
                continue
            rows.append(
                ProductVariant(
                    product_id=product_id,
                    sku=sku,
                    size=str(v.get("size") or "").strip() or None,
                    color=str(v.get("color") or "").strip() or None,
                    price=v.get("price"),
                    stock=v.get("stock"),
                    external_id=v.get("external_id"),
                    sort_order=v.get("sort_order", idx),
                )
            )
        return rows

    @staticmethod
    def _attr_rows(product_id: int, attributes: list) -> list:
        """Строки ProductAttribute из данных парсера (пустые name/value пропускаются)."""
        rows = []
        for idx, attr in enumerate(attributes):
            if not attr.get("name") or not attr.get("value"):
                continue
            rows.append(
                ProductAttribute(
                    product_id=product_id,
                    name=str(attr["name"]).strip(),
                    value=str(attr["value"]).strip(),
                    platform_attribute_id=attr.get("platform_attribute_id"),
                    sort_order=attr.get("sort_order", idx),
                )
            )
        return rows

    def bulk_import(
        self,
        user_id: int,
        source_label: str,
        mode: str,
        products_data: list,
        chunk_size: int = 200,
    ) -> tuple[int, int]:
        """
        P-2: пакетная запись распарсенных товаров (create/upsert).

        Было: 4 сессии БД и 2-4 commit'а на КАЖДЫЙ товар
        (repo.add + find_by_external + set_variants + set_attributes).
        Стало: одна сессия на весь импорт, существующие карточки для upsert
        выбираются одним запросом на чанк, варианты/атрибуты вставляются пачкой,
        один commit на чанк (по умолчанию 200 товаров).

        Возвращает (imported, updated).
        """
        imported = 0
        updated = 0

        with SessionLocal() as db:
            for offset in range(0, len(products_data), chunk_size):
                chunk = products_data[offset : offset + chunk_size]

                # --- предвыборка существующих для upsert (один запрос на чанк) ---
                existing_by_key: dict = {}
                if mode == "upsert":
                    conds = []
                    ext_ids = [str(p.get("external_id")) for p in chunk if p.get("external_id")]
                    skus = [str(p.get("sku")) for p in chunk if p.get("sku")]
                    if ext_ids:
                        conds.append(Product.external_id.in_(ext_ids))
                    if skus:
                        conds.append(Product.sku.in_(skus))
                    if conds:
                        rows = (
                            db.query(Product)
                            .filter(
                                Product.user_id == user_id,
                                Product.source == source_label,
                                or_(*conds),
                            )
                            .all()
                        )
                        for r in rows:
                            if r.external_id:
                                existing_by_key[f"ext:{r.external_id}"] = r
                            if r.sku:
                                existing_by_key[f"sku:{r.sku}"] = r

                new_products: list = []
                jobs: list = []  # (orm, variants, attrs)

                for p_data in chunk:
                    payload, variants, attributes = self._import_payload(
                        p_data, user_id, source_label
                    )

                    existing = None
                    if mode == "upsert":
                        ext = p_data.get("external_id")
                        sku = p_data.get("sku")
                        if ext:
                            existing = existing_by_key.get(f"ext:{str(ext)}")
                        if existing is None and sku:
                            existing = existing_by_key.get(f"sku:{str(sku)}")

                    if existing is not None:
                        # upsert: обновляем колонки на месте
                        for key, value in payload.items():
                            if key == "user_id":
                                continue
                            setattr(existing, key, value)
                        jobs.append((existing, variants, attributes))
                        updated += 1
                    else:
                        obj = Product(**payload)
                        new_products.append(obj)
                        jobs.append((obj, variants, attributes))

                if new_products:
                    db.add_all(new_products)
                    db.flush()  # присваиваем id новым товарам (без commit)

                # --- варианты/характеристики всего чанка одним пакетом ---
                replace_variant_ids = [p.id for (p, v, _) in jobs if v]
                replace_attr_ids = [p.id for (p, _, a) in jobs if a]
                if replace_variant_ids:
                    db.query(ProductVariant).filter(
                        ProductVariant.product_id.in_(replace_variant_ids)
                    ).delete(synchronize_session=False)
                if replace_attr_ids:
                    db.query(ProductAttribute).filter(
                        ProductAttribute.product_id.in_(replace_attr_ids)
                    ).delete(synchronize_session=False)

                var_rows: list = []
                attr_rows: list = []
                for p, variants, attributes in jobs:
                    if variants:
                        var_rows.extend(self._variant_rows(p.id, variants))
                    if attributes:
                        attr_rows.extend(self._attr_rows(p.id, attributes))
                if var_rows:
                    db.add_all(var_rows)
                if attr_rows:
                    db.add_all(attr_rows)

                db.commit()
                imported += len(new_products)

        return imported, updated
