"""Репозиторий товаров: CRUD, фильтрация, пагинация, массовые операции (P-2/P-3).

Dual-Engine: синхронные методы (для Celery и сервисов) + неблокирующие
методы на AsyncSession для роутеров FastAPI.
"""

from sqlalchemy import asc, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Product, ProductAttribute, ProductVariant
from database.session import SessionLocal


class ProductRepository:

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

    @staticmethod
    def _apply_filters(query, user_id, is_admin, search, status, source):
        if not is_admin and user_id is not None:
            query = query.filter(Product.user_id == user_id)
        if search:
            query = query.filter(Product.name.ilike(f"%{search}%"))
        if status:
            query = query.filter(Product.status == status)
        if source:
            query = query.filter(Product.source.ilike(f"%{source}%"))
        return query

    @staticmethod
    def _apply_async_filters(stmt, user_id, is_admin, search, status, source):
        if not is_admin and user_id is not None:
            stmt = stmt.where(Product.user_id == user_id)
        if search:
            stmt = stmt.where(Product.name.ilike(f"%{search}%"))
        if status:
            stmt = stmt.where(Product.status == status)
        if source:
            stmt = stmt.where(Product.source.ilike(f"%{source}%"))
        return stmt

    # ---------- асинхронные методы для FastAPI (AsyncSession + asyncpg) ----------
    async def get_all_async(
        self,
        db: AsyncSession,
        user_id: int = None,
        is_admin: bool = False,
        search: str | None = None,
        status: str | None = None,
        source: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        """Неблокирующее получение товаров с фильтрацией, сортировкой и пагинацией."""
        count_stmt = select(func.count(Product.id))
        count_stmt = self._apply_async_filters(
            count_stmt, user_id, is_admin, search, status, source
        )
        total_res = await db.execute(count_stmt)
        total = int(total_res.scalar() or 0)

        stmt = select(Product).options(
            selectinload(Product.attributes),
            selectinload(Product.variants),
        )
        stmt = self._apply_async_filters(stmt, user_id, is_admin, search, status, source)

        sort_column = getattr(Product, sort_by, Product.created_at)
        stmt = stmt.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))
        stmt = stmt.offset(skip).limit(limit)

        res = await db.execute(stmt)
        products = res.scalars().all()

        return {
            "total": total,
            "products": [self._to_dict(p) for p in products],
        }

    async def get_by_id_async(
        self, db: AsyncSession, product_id: int, user_id: int = None, is_admin: bool = False
    ) -> dict | None:
        """Неблокирующее получение ОДНОГО товара по ID (модалки миграции/редактирования).

        Важно: читает СВЕЖИЕ данные из БД, а не из кэша фронтенда — после
        «Заполнить пропуски» / массового обновления цена и поля уже актуальны.
        """
        stmt = (
            select(Product)
            .options(selectinload(Product.attributes), selectinload(Product.variants))
            .where(Product.id == product_id)
        )
        if not is_admin and user_id is not None:
            stmt = stmt.where(Product.user_id == user_id)

        res = await db.execute(stmt)
        product = res.scalars().first()
        return self._to_dict(product)

    async def get_stats_async(
        self,
        db: AsyncSession,
        user_id: int = None,
        is_admin: bool = False,
    ) -> dict:
        """Неблокирующее получение статистики одним SQL-запросом."""
        stmt = select(
            func.count(Product.id).label("total"),
            func.coalesce(
                func.sum(case((Product.status == "pending", 1), else_=0)), 0
            ).label("pending"),
            func.coalesce(
                func.sum(case((Product.status == "success", 1), else_=0)), 0
            ).label("success"),
            func.coalesce(
                func.sum(case((Product.status == "error", 1), else_=0)), 0
            ).label("error"),
            func.coalesce(
                func.sum(case((Product.status == "processing", 1), else_=0)), 0
            ).label("processing"),
        )
        if not is_admin and user_id is not None:
            stmt = stmt.where(Product.user_id == user_id)

        res = await db.execute(stmt)
        row = res.one()
        return {
            "total": int(row.total or 0),
            "pending": int(row.pending or 0),
            "success": int(row.success or 0),
            "error": int(row.error or 0),
            "processing": int(row.processing or 0),
        }

    # ---------- чтение (синхронный контур) ----------
    def get_all(
        self,
        user_id: int = None,
        is_admin: bool = False,
        search: str | None = None,
        status: str | None = None,
        source: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ):
        """Получить товары с фильтрацией, сортировкой и пагинацией."""
        with SessionLocal() as db:
            # ✅ ОПТИМИЗАЦИЯ: Eager loading предотвращает N+1 запросов для attributes и variants
            query = db.query(Product).options(
                selectinload(Product.attributes), selectinload(Product.variants)
            )
            query = self._apply_filters(query, user_id, is_admin, search, status, source)

            total = query.count()

            sort_column = getattr(Product, sort_by, Product.created_at)
            query = query.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

            products = query.offset(skip).limit(limit).all()

            return {
                "total": total,
                "products": [self._to_dict(p) for p in products],
            }

    def get_by_id(self, product_id: int, user_id: int = None):
        """Получить товар по ID. Если указан user_id — проверяет владельца."""
        with SessionLocal() as db:
            # ✅ ОПТИМИЗАЦИЯ: Eager loading для модалок редактирования
            query = (
                db.query(Product)
                .options(selectinload(Product.attributes), selectinload(Product.variants))
                .filter(Product.id == product_id)
            )

            if user_id is not None:
                query = query.filter(Product.user_id == user_id)

            return self._to_dict(query.first())

    def find_by_external(
        self, user_id: int, source: str, external_id: str = None, sku: str = None
    ) -> dict | None:
        """Найти существующий товар по external_id или sku (для upsert при повторном импорте)."""
        with SessionLocal() as db:
            # ✅ ОПТИМИЗАЦИЯ: Eager loading на случай, если потребуется сериализация
            query = (
                db.query(Product)
                .options(selectinload(Product.attributes), selectinload(Product.variants))
                .filter(
                    Product.user_id == user_id,
                    Product.source == source,
                )
            )
            if external_id:
                query = query.filter(Product.external_id == external_id)
            elif sku:
                query = query.filter(Product.sku == sku)
            else:
                return None
            return self._to_dict(query.first())

    # ---------- запись ----------
    def add(self, product_data):
        """Добавить новый товар. product_data должен содержать user_id."""
        with SessionLocal() as db:
            if hasattr(product_data, "model_dump"):
                data_dict = product_data.model_dump()
            else:
                data_dict = dict(product_data)
            data_dict.pop("id", None)

            if not data_dict.get("user_id"):
                raise ValueError("user_id обязателен при создании товара")

            new_product = Product(**data_dict)
            db.add(new_product)
            db.commit()
            db.refresh(new_product)
            return self._to_dict(new_product)

    def update(self, product_id: int, update_data: dict, user_id: int = None):
        """Обновить товар. Если указан user_id — проверяет владельца."""
        with SessionLocal() as db:
            query = db.query(Product).filter(Product.id == product_id)
            if user_id is not None:
                query = query.filter(Product.user_id == user_id)
            product = query.first()
            if product:
                for key, value in update_data.items():
                    setattr(product, key, value)
                db.commit()
                db.refresh(product)
                return self._to_dict(product)
            return None

    def bulk_update(self, product_ids: list[int], update_data: dict, user_id: int = None) -> int:
        """Массовое обновление товаров. Возвращает кол-во обновлённых строк."""
        if not product_ids or not update_data:
            return 0
        with SessionLocal() as db:
            query = db.query(Product).filter(Product.id.in_(product_ids))
            if user_id is not None:
                query = query.filter(Product.user_id == user_id)
            updated = query.update(update_data, synchronize_session=False)
            db.commit()
            return updated

    def update_batch(self, updates: list[tuple[int, dict]], user_id: int = None) -> int:
        """P-3: массовое обновление РАЗНЫМИ данными — одна сессия и один commit
        вместо сессии+commit на каждый товар (пакетная миграция)."""
        if not updates:
            return 0
        applied = 0
        with SessionLocal() as db:
            ids = [pid for pid, _ in updates]
            query = db.query(Product).filter(Product.id.in_(ids))
            if user_id is not None:
                query = query.filter(Product.user_id == user_id)
            by_id = {p.id: p for p in query.all()}
            for pid, data in updates:
                p = by_id.get(pid)
                if not p:
                    continue
                for key, value in data.items():
                    setattr(p, key, value)
                applied += 1
            db.commit()
        return applied

    def get_by_ids(self, user_id: int, product_ids: list, chunk_size: int = 100) -> dict:
        """P-3: выборка пакета товаров одним selectinload-запросом на чанк
        вместо get_by_id() по одному (сессия на каждый товар → 1 на чанк).
        Возвращает {product_id: dict}."""
        result: dict = {}
        if not product_ids:
            return result
        with SessionLocal() as db:
            for offset in range(0, len(product_ids), chunk_size):
                chunk = product_ids[offset : offset + chunk_size]
                rows = (
                    db.query(Product)
                    .options(selectinload(Product.attributes), selectinload(Product.variants))
                    .filter(Product.user_id == user_id, Product.id.in_(chunk))
                    .all()
                )
                for p in rows:
                    result[p.id] = self._to_dict(p)
        return result

    def delete(self, product_id: int, user_id: int = None):
        """Удалить товар. Если указан user_id — проверяет владельца."""
        with SessionLocal() as db:
            query = db.query(Product).filter(Product.id == product_id)
            if user_id is not None:
                query = query.filter(Product.user_id == user_id)
            product = query.first()
            if product:
                db.delete(product)
                db.commit()
                return True
            return False

    # ---------- P-2: пакетный импорт ----------

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

    # ---------- статистика ----------
    def get_stats(self, user_id: int = None, is_admin: bool = False):
        """Статистика по товарам одним SQL-запросом (P-6).

        Раньше: 5 отдельных COUNT-запросов к одной таблице.
        """
        with SessionLocal() as db:
            stmt = select(
                func.count(Product.id).label("total"),
                func.coalesce(
                    func.sum(case((Product.status == "pending", 1), else_=0)), 0
                ).label("pending"),
                func.coalesce(
                    func.sum(case((Product.status == "success", 1), else_=0)), 0
                ).label("success"),
                func.coalesce(
                    func.sum(case((Product.status == "error", 1), else_=0)), 0
                ).label("error"),
                func.coalesce(
                    func.sum(case((Product.status == "processing", 1), else_=0)), 0
                ).label("processing"),
            )
            if not is_admin and user_id is not None:
                stmt = stmt.where(Product.user_id == user_id)

            row = db.execute(stmt).one()
            return {
                "total": int(row.total or 0),
                "pending": int(row.pending or 0),
                "success": int(row.success or 0),
                "error": int(row.error or 0),
                "processing": int(row.processing or 0),
            }


# Глобальный экземпляр (совместимость импортов: from database.repository import repo)
repo = ProductRepository()
