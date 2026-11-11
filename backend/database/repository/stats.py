"""Запись и агрегация статистики операций (P-6: агрегация в SQL)."""

from sqlalchemy import case, func

from database.models import ImportExportStats
from database.session import SessionLocal
from core.time import utcnow


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
        """
        Сводная статистика операций за период (P-6: вся агрегация в SQL).

        Раньше: q.all() — ВСЕ строки за период выгружались в память
        и считались в Python. Для админа за 90 дней это десятки тысяч строк.
        Стало: 4 компактных GROUP BY-запроса к БД.
        """
        from datetime import datetime, timedelta

        since = utcnow() - timedelta(days=days)

        with SessionLocal() as db:
            base = db.query(ImportExportStats).filter(ImportExportStats.created_at >= since)
            if not is_admin:
                base = base.filter(ImportExportStats.user_id == user_id)

            # --- итоги одним запросом ---
            tot = base.with_entities(
                func.count(ImportExportStats.id),
                func.sum(case((ImportExportStats.status == "success", 1), else_=0)),
                func.sum(case((ImportExportStats.status == "partial", 1), else_=0)),
                func.sum(case((ImportExportStats.status == "error", 1), else_=0)),
            ).one()
            operations, success, partial, error = (int(t or 0) for t in tot)
            totals = {
                "operations": operations,
                "success": success,
                "partial": partial,
                "error": error,
            }
            ok = success + partial
            success_rate = round(ok / operations * 100, 1) if operations else 0.0

            avg_row = base.with_entities(
                func.coalesce(func.avg(ImportExportStats.duration_ms), 0)
            ).scalar()
            avg_duration_ms = int(avg_row or 0)

            # --- активность по дням (GROUP BY date(operation)) ---
            day_expr = func.date(ImportExportStats.created_at)
            day_rows = (
                base.with_entities(
                    day_expr.label("day"),
                    ImportExportStats.operation,
                    func.count(ImportExportStats.id).label("cnt"),
                    func.sum(
                        case((ImportExportStats.status == "error", 1), else_=0)
                    ).label("errors"),
                )
                .group_by(day_expr, ImportExportStats.operation)
                .all()
            )
            by_day = {}
            for i in range(days):
                d = (utcnow() - timedelta(days=days - 1 - i)).date()
                by_day[d.isoformat()] = {
                    "date": d.isoformat(),
                    "import": 0,
                    "export": 0,
                    "migrate": 0,
                    "other": 0,
                    "error": 0,
                }
            for row in day_rows:
                # PG: func.date() -> datetime.date; SQLite: str
                if hasattr(row.day, "isoformat"):
                    key = row.day.isoformat()
                else:
                    key = str(row.day) if row.day else None
                if key not in by_day:
                    continue
                b = by_day[key]
                op = row.operation or ""
                cnt = int(row.cnt or 0)
                if op.startswith("import"):
                    b["import"] += cnt
                elif op == "export":
                    b["export"] += cnt
                elif op == "migrate":
                    b["migrate"] += cnt
                else:
                    b["other"] += cnt
                b["error"] += int(row.errors or 0)

            # --- по типам операций ---
            op_rows = (
                base.with_entities(
                    ImportExportStats.operation,
                    func.count(ImportExportStats.id).label("cnt"),
                    func.sum(
                        case((ImportExportStats.status == "error", 1), else_=0)
                    ).label("errors"),
                    func.coalesce(func.sum(ImportExportStats.success_items), 0).label("items"),
                )
                .group_by(ImportExportStats.operation)
                .all()
            )
            by_op = {}
            for r in op_rows:
                cnt = int(r.cnt or 0)
                errs = int(r.errors or 0)
                by_op[r.operation] = {
                    "operation": r.operation,
                    "count": cnt,
                    "success": cnt - errs,
                    "error": errs,
                    "items": int(r.items or 0),
                }

            # --- по площадкам ---
            plat_rows = (
                base.with_entities(
                    ImportExportStats.platform,
                    func.count(ImportExportStats.id).label("cnt"),
                    func.coalesce(func.sum(ImportExportStats.success_items), 0).label("items"),
                )
                .filter(ImportExportStats.platform.isnot(None))
                .group_by(ImportExportStats.platform)
                .all()
            )
            by_platform = {
                r.platform: {
                    "platform": r.platform,
                    "count": int(r.cnt or 0),
                    "items": int(r.items or 0),
                }
                for r in plat_rows
            }

        return {
            "period_days": days,
            "totals": totals,
            "success_rate": success_rate,
            "avg_duration_ms": avg_duration_ms,
            "by_day": list(by_day.values()),
            "by_operation": sorted(by_op.values(), key=lambda x: -x["count"]),
            "by_platform": sorted(by_platform.values(), key=lambda x: -x["count"]),
        }


# Глобальный экземпляр (совместимость импортов: from database.repository import stats_repo)
stats_repo = StatsRepository()
