"""Р1: гарантия, что разбиение routers/export.py на пакет не потеряло ни один маршрут.

Импортирует собранный роутер и сверяет таблицу (path, methods) с полным
списком эндпоинтов монолита (15 маршрутов). Если после рефакторинга
какой-то декоратор потерялся или путь изменился — тест упадёт.

Маршруты собираем через OpenAPI-схему (хелпер served_routes из
_route_helpers.py) — версионно-стойко для FastAPI/Starlette.
"""

from _route_helpers import served_routes

EXPECTED_ROUTES = {
    ("/api/export/ozon-template/upload", "POST"),
    ("/api/export/ozon-template/list", "GET"),
    ("/api/export/ozon-template/meta", "GET"),
    ("/api/export/ozon-template/status", "GET"),
    ("/api/export/ozon-template/download", "GET"),
    ("/api/export/ozon-template", "DELETE"),
    ("/api/export/preview/{platform}", "GET"),
    ("/api/export/template/{platform}", "GET"),
    ("/api/export/platform/{platform}", "GET"),
    ("/api/export/validate/{platform}", "GET"),
    ("/api/export/report", "GET"),
    ("/api/export/xlsx/{platform}", "GET"),
    ("/api/export/xlsx/{platform}/async", "POST"),
    ("/api/export/tasks/{task_id}", "GET"),
    ("/api/export/tasks/{task_id}/download", "GET"),
}


def test_export_router_routes_preserved():
    from routers import export

    actual = served_routes(export.router)

    missing = EXPECTED_ROUTES - actual
    extra = actual - EXPECTED_ROUTES
    assert not missing, f"Потеряны маршруты при разбиении пакета: {sorted(missing)}"
    assert not extra, f"Появились неожидаемые маршруты: {sorted(extra)}"


def test_export_router_prefix_and_tag():
    from routers import export

    assert export.router.prefix == "/api"
    assert "Export" in export.router.tags


# ==================== О2: инкрементальный предикат превью ====================


def test_is_changed_since_predicate():
    """Пустой last_export_at — новый товар; updated_at > last_export_at — изменённый."""
    from datetime import datetime

    from routers.export._queries import is_changed_since

    t0 = datetime(2026, 1, 1, 12, 0)
    t_later = datetime(2026, 1, 2, 12, 0)

    assert is_changed_since({"last_export_at": None, "updated_at": t_later}) is True
    assert is_changed_since({"last_export_at": t0, "updated_at": t_later}) is True
    assert is_changed_since({"last_export_at": t0, "updated_at": t0}) is False
    # updated_at отсутствует — товар не менялся после выгрузки
    assert is_changed_since({"last_export_at": t0, "updated_at": None}) is False


def test_category_counts_route_registered():
    """О3: лёгкий эндпоинт счётчиков категорий зарегистрирован в роутере товаров."""
    from routers import products as products_router

    paths = {path for path, _ in served_routes(products_router.router)}
    assert "/api/products/category-counts" in paths
