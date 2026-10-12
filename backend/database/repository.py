"""
Репозиторий для работы с товарами в базе данных.
Поддерживает фильтрацию, сортировку, пагинацию, массовые операции.
Схему БД ведёт ТОЛЬКО Alembic (create_all не вызываем).

✅ v2 Оптимизация: добавлен selectinload для предотвращения N+1 запросов
при загрузке товаров с их атрибутами и вариациями.
"""


from sqlalchemy import asc, desc
from sqlalchemy.orm import selectinload

from database.models import (
    FileOperationLog,
    ImportExportStats,
    MigrationLog,
    Product,
    ProductAttribute,
    ProductVariant,
)
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
            "price": p.price,
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
                    "price": v.price,
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

    # ---------- чтение ----------
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

    # ---------- статистика ----------
    def get_stats(self, user_id: int = None, is_admin: bool = False):
        """Получить статистику по товарам."""
        with SessionLocal() as db:
            query = db.query(Product)
            if not is_admin and user_id is not None:
                query = query.filter(Product.user_id == user_id)
            total = query.count()
            pending = query.filter(Product.status == "pending").count()
            success = query.filter(Product.status == "success").count()
            error = query.filter(Product.status == "error").count()
            processing = query.filter(Product.status == "processing").count()
            return {
                "total": total,
                "pending": pending,
                "success": success,
                "error": error,
                "processing": processing,
            }


class OperationLogRepository:
    """Репозиторий журнала операций (импорт/экспорт/миграции)"""

    def log_file_operation(
        self,
        user_id: int,
        operation: str,
        platform: str = None,
        filename: str = None,
        mode: str = None,
        status: str = "success",
        total_rows: int = 0,
        imported: int = 0,
        updated: int = 0,
        failed: int = 0,
        errors: list = None,
    ) -> int:
        with SessionLocal() as db:
            entry = FileOperationLog(
                user_id=user_id,
                operation=operation,
                platform=platform,
                filename=filename,
                mode=mode,
                status=status,
                total_rows=total_rows,
                imported=imported,
                updated=updated,
                failed=failed,
                errors=errors or [],
            )
            db.add(entry)
            db.commit()
            return entry.id

    def log_migration(
        self,
        user_id: int,
        product_id: int,
        product_name: str,
        source_platform: str,
        target_platform: str,
        old_price: float = None,
        new_price: float = None,
        old_category: str = None,
        new_category: str = None,
        status: str = "success",
        error_message: str = None,
        is_batch: bool = False,
        batch_id: str = None,
    ) -> int:
        with SessionLocal() as db:
            entry = MigrationLog(
                user_id=user_id,
                product_id=product_id,
                product_name=product_name,
                source_platform=source_platform,
                target_platform=target_platform,
                old_price=old_price,
                new_price=new_price,
                old_category=old_category,
                new_category=new_category,
                status=status,
                error_message=error_message,
                is_batch=is_batch,
                batch_id=batch_id,
            )
            db.add(entry)
            db.commit()
            return entry.id

    @staticmethod
    def _file_desc(e) -> str:
        if e.operation == "export":
            return f"Выгрузка XLSX для {e.platform or '?'}"
        if e.operation == "media_download":
            return f"💾 Скачивание копий фото ({e.filename})"
        if e.operation == "import_file":
            return f"Импорт файла «{e.filename}» ({e.platform or '?'}, режим {e.mode or 'create'})"
        if e.operation == "import_yml":
            return f"Импорт YML-фида ({e.platform or '?'})"
        return f"Импорт по ключу ({e.platform or '?'})"

    def get_history(
        self,
        user_id: int,
        is_admin: bool = False,
        operation: str = None,
        limit: int = 50,
        skip: int = 0,
    ) -> list:
        """Единая лента истории: файлы + миграции, отсортированные по дате."""
        entries = []

        with SessionLocal() as db:
            if operation in (None, "", "import", "export"):
                q = db.query(FileOperationLog)
                if not is_admin:
                    q = q.filter(FileOperationLog.user_id == user_id)
                if operation == "import":
                    q = q.filter(FileOperationLog.operation.like("import%"))
                elif operation == "export":
                    q = q.filter(FileOperationLog.operation == "export")
                for e in q.all():
                    entries.append(
                        {
                            "id": f"file-{e.id}",
                            "type": (
                                "import"
                                if e.operation.startswith("import")
                                else ("media" if e.operation == "media_download" else "export")
                            ),
                            "operation": e.operation,
                            "platform": e.platform,
                            "description": self._file_desc(e),
                            "counts": (
                                f"создано {e.imported} / обновлено {e.updated} / ошибок {e.failed}"
                                if e.operation.startswith("import")
                                else (
                                    f"сохранено {e.imported} из {e.total_rows}"
                                    if e.operation == "media_download"
                                    else f"{e.total_rows} строк"
                                )
                            ),
                            "status": e.status,
                            "created_at": e.created_at.isoformat() if e.created_at else None,
                        }
                    )

            if operation in (None, "", "migration"):
                q = db.query(MigrationLog)
                if not is_admin:
                    q = q.filter(MigrationLog.user_id == user_id)
                for m in q.all():
                    entries.append(
                        {
                            "id": f"mig-{m.id}",
                            "type": "migration",
                            "operation": "batch" if m.is_batch else "single",
                            "platform": m.target_platform,
                            "description": f"«{m.product_name}» → {m.target_platform}",
                            "counts": f"{m.old_price} → {m.new_price} ₽",
                            "status": m.status,
                            "error_message": m.error_message,
                            "created_at": m.created_at.isoformat() if m.created_at else None,
                        }
                    )

        entries.sort(key=lambda x: x["created_at"] or "", reverse=True)
        return entries[skip : skip + limit]


class AttributeRepository:
    """Репозиторий характеристик товаров"""

    @staticmethod
    def _to_dict(attr) -> dict:
        return {
            "id": attr.id,
            "product_id": attr.product_id,
            "name": attr.name,
            "value": attr.value,
            "platform_attribute_id": attr.platform_attribute_id,
            "sort_order": attr.sort_order,
        }

    def get_by_product(self, product_id: int) -> list[dict]:
        """Получить все характеристики товара"""
        with SessionLocal() as db:
            attrs = (
                db.query(ProductAttribute)
                .filter(ProductAttribute.product_id == product_id)
                .order_by(ProductAttribute.sort_order)
                .all()
            )
            return [self._to_dict(a) for a in attrs]

    def set_attributes(self, product_id: int, attributes: list[dict]) -> list[dict]:
        """
        Заменить все характеристики товара на новые.
        Используется при импорте и массовом редактировании.
        """
        with SessionLocal() as db:
            # Удаляем старые
            db.query(ProductAttribute).filter(ProductAttribute.product_id == product_id).delete()

            # Создаём новые
            result = []
            for idx, attr in enumerate(attributes):
                if not attr.get("name") or not attr.get("value"):
                    continue
                new_attr = ProductAttribute(
                    product_id=product_id,
                    name=str(attr["name"]).strip(),
                    value=str(attr["value"]).strip(),
                    platform_attribute_id=attr.get("platform_attribute_id"),
                    sort_order=attr.get("sort_order", idx),
                )
                db.add(new_attr)
                db.flush()
                result.append(self._to_dict(new_attr))
            db.commit()
            return result

    def add_attribute(
        self, product_id: int, name: str, value: str, platform_attribute_id: str = None
    ) -> dict:
        """Добавить одну характеристику"""
        with SessionLocal() as db:
            max_order = (
                db.query(ProductAttribute.sort_order)
                .filter(ProductAttribute.product_id == product_id)
                .order_by(ProductAttribute.sort_order.desc())
                .first()
            )
            next_order = (max_order[0] or 0) + 1 if max_order else 0

            new_attr = ProductAttribute(
                product_id=product_id,
                name=str(name).strip(),
                value=str(value).strip(),
                platform_attribute_id=platform_attribute_id,
                sort_order=next_order,
            )
            db.add(new_attr)
            db.commit()
            db.refresh(new_attr)
            return self._to_dict(new_attr)

    def delete_attribute(self, attribute_id: int, user_id: int = None) -> bool:
        """Удалить характеристику (с проверкой владельца товара)"""
        with SessionLocal() as db:
            attr = db.query(ProductAttribute).filter(ProductAttribute.id == attribute_id).first()
            if not attr:
                return False
            if user_id is not None:
                product = db.query(Product).filter(Product.id == attr.product_id).first()
                if not product or product.user_id != user_id:
                    return False
            db.delete(attr)
            db.commit()
            return True


class VariantRepository:
    """Репозиторий вариаций товаров"""

    @staticmethod
    def _to_dict(v) -> dict:
        return {
            "id": v.id,
            "product_id": v.product_id,
            "sku": v.sku,
            "size": v.size,
            "color": v.color,
            "price": v.price,
            "stock": v.stock,
            "external_id": v.external_id,
            "sort_order": v.sort_order,
        }

    def get_by_product(self, product_id: int) -> list[dict]:
        with SessionLocal() as db:
            variants = (
                db.query(ProductVariant)
                .filter(ProductVariant.product_id == product_id)
                .order_by(ProductVariant.sort_order)
                .all()
            )
            return [self._to_dict(v) for v in variants]

    def set_variants(self, product_id: int, variants: list[dict]) -> list[dict]:
        """Полностью заменить набор вариаций товара"""
        with SessionLocal() as db:
            db.query(ProductVariant).filter(ProductVariant.product_id == product_id).delete()

            result = []
            for idx, v in enumerate(variants):
                sku = str(v.get("sku") or "").strip()
                if not sku:
                    continue
                new_v = ProductVariant(
                    product_id=product_id,
                    sku=sku,
                    size=str(v.get("size") or "").strip() or None,
                    color=str(v.get("color") or "").strip() or None,
                    price=v.get("price"),
                    stock=v.get("stock"),
                    external_id=v.get("external_id"),
                    sort_order=v.get("sort_order", idx),
                )
                db.add(new_v)
                db.flush()
                result.append(self._to_dict(new_v))
            db.commit()
            return result

    def delete_variant(self, variant_id: int, user_id: int = None) -> bool:
        with SessionLocal() as db:
            v = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
            if not v:
                return False
            if user_id is not None:
                product = db.query(Product).filter(Product.id == v.product_id).first()
                if not product or product.user_id != user_id:
                    return False
            db.delete(v)
            db.commit()
            return True


class StatsRepository:
    """Запись и агрегация статистики операций"""

    def record(
        self,
        user_id: int,
        operation: str,
        platform: str = None,
        status: str = "success",
        total_items: int = 0,
        success_items: int = 0,
        failed_items: int = 0,
        duration_ms: int = 0,
    ) -> int:
        with SessionLocal() as db:
            row = ImportExportStats(
                user_id=user_id,
                operation=operation,
                platform=platform,
                status=status,
                total_items=total_items,
                success_items=success_items,
                failed_items=failed_items,
                duration_ms=duration_ms,
            )
            db.add(row)
            db.commit()
            return row.id

    def get_dashboard(self, user_id: int, days: int = 7, is_admin: bool = False) -> dict:
        from datetime import datetime, timedelta

        since = datetime.utcnow() - timedelta(days=days)

        with SessionLocal() as db:
            q = db.query(ImportExportStats).filter(ImportExportStats.created_at >= since)
            if not is_admin:
                q = q.filter(ImportExportStats.user_id == user_id)
            rows = q.all()

        totals = {
            "operations": len(rows),
            "success": sum(1 for r in rows if r.status == "success"),
            "partial": sum(1 for r in rows if r.status == "partial"),
            "error": sum(1 for r in rows if r.status == "error"),
        }
        ok = totals["success"] + totals["partial"]
        success_rate = round(ok / totals["operations"] * 100, 1) if totals["operations"] else 0.0

        durations = [r.duration_ms for r in rows if r.duration_ms]
        avg_duration_ms = int(sum(durations) / len(durations)) if durations else 0

        # --- Активность по дням ---
        by_day = {}
        for i in range(days):
            d = (datetime.utcnow() - timedelta(days=days - 1 - i)).date()
            by_day[d.isoformat()] = {
                "date": d.isoformat(),
                "import": 0,
                "export": 0,
                "migrate": 0,
                "other": 0,
                "error": 0,
            }
        for r in rows:
            key = r.created_at.date().isoformat() if r.created_at else None
            if key not in by_day:
                continue
            b = by_day[key]
            if r.status == "error":
                b["error"] += 1
            if r.operation.startswith("import"):
                b["import"] += 1
            elif r.operation == "export":
                b["export"] += 1
            elif r.operation == "migrate":
                b["migrate"] += 1
            else:
                b["other"] += 1

        # --- По типам операций ---
        by_op: dict[str, dict] = {}
        for r in rows:
            b = by_op.setdefault(
                r.operation,
                {
                    "operation": r.operation,
                    "count": 0,
                    "success": 0,
                    "error": 0,
                    "items": 0,
                },
            )
            b["count"] += 1
            b["error" if r.status == "error" else "success"] += 1
            b["items"] += r.success_items or 0

        # --- По площадкам ---
        by_platform: dict[str, dict] = {}
        for r in rows:
            if not r.platform:
                continue
            b = by_platform.setdefault(r.platform, {"platform": r.platform, "count": 0, "items": 0})
            b["count"] += 1
            b["items"] += r.success_items or 0

        return {
            "period_days": days,
            "totals": totals,
            "success_rate": success_rate,
            "avg_duration_ms": avg_duration_ms,
            "by_day": list(by_day.values()),
            "by_operation": sorted(by_op.values(), key=lambda x: -x["count"]),
            "by_platform": sorted(by_platform.values(), key=lambda x: -x["count"]),
        }


# Глобальные экземпляры репозиториев
stats_repo = StatsRepository()
variant_repo = VariantRepository()
attr_repo = AttributeRepository()
op_log = OperationLogRepository()
repo = ProductRepository()
