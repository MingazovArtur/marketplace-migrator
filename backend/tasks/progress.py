"""Чтение прогресса Celery-задачи по ID (для фронта и роутеров)."""

import logging

from celery_app import celery_app

logger = logging.getLogger(__name__)


def get_progress(task_id: str) -> dict:
    """
    Текущий прогресс задачи по ID: status ∈ pending|progress|completed|failed
    + total, done, success, errors, percent, error_details.
    """
    try:
        result = celery_app.AsyncResult(task_id)

        if result.state == "PROGRESS":
            meta = result.info or {}
            total = meta.get("total", 0)
            done = meta.get("done", 0)
            return {
                "status": "progress",
                "total": total,
                "done": done,
                "success": meta.get("success", 0),
                "errors": meta.get("errors", 0),
                "percent": meta.get("percent", int(done * 100 / total) if total else 0),
                "error_details": meta.get("error_details", []),
            }

        if result.state == "SUCCESS":
            r = result.result or {}
            if isinstance(r, dict):
                if r.get("status") == "error":
                    return {
                        "status": "failed",
                        "total": r.get("total", 0),
                        "done": r.get("done", 0),
                        "success": r.get("success", 0),
                        "errors": r.get("errors", 1),
                        "percent": 0,
                        "error": r.get("message") or "Ошибка загрузки спеков",
                        "error_details": r.get("error_details", []),
                    }
                if r.get("status") == "paused":
                    # Загрузка остановлена админом (POST /admin/specs-tasks/{id}/pause);
                    # продолжить можно на странице мониторинга спеков
                    total = r.get("total", 0)
                    return {
                        "status": "paused",
                        "total": total,
                        "done": total,
                        "success": r.get("success", 0),
                        "errors": r.get("errors", 0),
                        "percent": 0,
                        "message": r.get("message")
                        or "Загрузка поставлена на паузу администратором",
                    }
                total = r.get("total") or (r.get("fetched", 0) + r.get("errors", 0))
                success = r.get("success") or r.get("fetched", 0)
                errors = r.get("errors", 0)
                return {
                    "status": "completed",
                    "total": total,
                    "done": total,
                    "success": success,
                    "errors": errors,
                    "percent": 100,
                    "error_details": r.get("error_details", []),
                    "platform": r.get("platform"),
                    "filename": r.get("filename"),
                }
            return {
                "status": "completed",
                "total": 0,
                "done": 0,
                "success": 0,
                "errors": 0,
                "percent": 100,
            }

        if result.state == "FAILURE":
            return {
                "status": "failed",
                "total": 0,
                "done": 0,
                "success": 0,
                "errors": 0,
                "percent": 0,
                "error": str(result.info) if result.info else "Неизвестная ошибка",
            }

        return {"status": "pending", "total": 0, "done": 0, "success": 0, "errors": 0, "percent": 0}

    except Exception as e:
        logger.warning(f"Не удалось получить прогресс задачи {task_id}: {e}")
        return {
            "status": "failed",
            "total": 0,
            "done": 0,
            "success": 0,
            "errors": 0,
            "percent": 0,
            "error": str(e),
        }
