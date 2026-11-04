"""Репозиторий журнала операций (импорт/экспорт/миграции)."""

from database.models import FileOperationLog, MigrationLog
from database.session import SessionLocal


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

    def log_migration_batch(self, entries: list[dict]) -> int:
        """P-3: пакетная запись журнала миграций (bulk insert).

        entries — dicts с ключами, соответствующими колонкам MigrationLog
        (user_id, product_id, product_name, source_platform, target_platform,
        old_price, new_price, old_category, new_category, status, error_message,
        is_batch, batch_id). Заменяет commit на каждую запись при пакетной миграции.
        """
        if not entries:
            return 0
        with SessionLocal() as db:
            db.bulk_insert_mappings(MigrationLog, entries)
            db.commit()
            return len(entries)

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
        """Единая лента истории: файлы + миграции, отсортированные по дате.

        P-4: сортировка и окно выборки делаются в SQL (ORDER BY + LIMIT).
        Раньше обе таблицы выгружались ЦЕЛИКОМ в память
        (q.all() без лимита) и сортировались в Python — на десятках тысяч
        операций история тормозила и ела память.
        """
        file_entries = []
        mig_entries = []

        # из каждого источника достаточно вытащить skip+limit строк —
        # после слияния окно [skip : skip+limit] гарантированно покрыто
        window = skip + limit

        with SessionLocal() as db:
            if operation in (None, "", "import", "export"):
                q = db.query(FileOperationLog)
                if not is_admin:
                    q = q.filter(FileOperationLog.user_id == user_id)
                if operation == "import":
                    q = q.filter(FileOperationLog.operation.like("import%"))
                elif operation == "export":
                    q = q.filter(FileOperationLog.operation == "export")
                for e in (
                    q.order_by(
                        FileOperationLog.created_at.desc(), FileOperationLog.id.desc()
                    )
                    .limit(window)
                    .all()
                ):
                    file_entries.append(
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
                for m in (
                    q.order_by(MigrationLog.created_at.desc(), MigrationLog.id.desc())
                    .limit(window)
                    .all()
                ):
                    mig_entries.append(
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

        merged = sorted(
            file_entries + mig_entries,
            key=lambda x: (x["created_at"] or "", x["id"]),
            reverse=True,
        )
        return merged[skip : skip + limit]


# Глобальный экземпляр (совместимость импортов: from database.repository import op_log)
op_log = OperationLogRepository()
