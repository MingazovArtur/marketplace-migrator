"""Р7: гарантия, что разбиение routers/categories.py на пакет не потеряло маршруты.

Сверяет таблицу (path, methods) с полным списком эндпоинтов монолита
(17 маршрутов) через OpenAPI-схему (served_routes) — версионно-стойко.

Отдельно проверяет ПОРЯДОК матчинга: фиксированные пути
(/specs/{platform}/names, /key-source, /refresh/.../progress) обязаны
срабатывать раньше catch-all /specs/{platform}/{category_id:path} —
иначе «names» ловился бы как category_id (регрессия original-бага,
описанного в docstring пакета).
"""

from _route_helpers import served_routes

EXPECTED_ROUTES = {
    ("/api/specs/{platform}/refresh", "POST"),
    ("/api/specs/{platform}/refresh/{task_id}/progress", "GET"),
    ("/api/specs/{platform}/refresh/{task_id}/events", "GET"),
    ("/api/admin/specs-tasks", "GET"),
    ("/api/admin/specs-tasks/events", "GET"),
    ("/api/admin/specs-tasks/{task_id}/pause", "POST"),
    ("/api/admin/specs-tasks/{task_id}/resume", "POST"),
    ("/api/specs/{platform}/key-source", "GET"),
    ("/api/specs/{platform}/names", "GET"),
    ("/api/specs/{platform}", "GET"),
    ("/api/specs/{platform}", "DELETE"),
    ("/api/specs/{platform}/{category_id}", "DELETE"),
    ("/api/specs/{platform}/{category_id}", "GET"),
    ("/api/categories/{platform}", "GET"),
    ("/api/categories/{platform}/tree", "GET"),
    ("/api/categories/{platform}/refresh", "POST"),
    ("/api/category-mapping", "GET"),
    ("/api/category-mapping", "POST"),
    ("/api/category-mapping/{mapping_id}", "DELETE"),
}


def test_categories_router_routes_preserved():
    from routers import categories

    actual = served_routes(categories.router)

    missing = EXPECTED_ROUTES - actual
    extra = actual - EXPECTED_ROUTES
    assert not missing, f"Потеряны маршруты при разбиении пакета: {sorted(missing)}"
    assert not extra, f"Появились неожидаемые маршруты: {sorted(extra)}"


def test_categories_router_prefix_and_tag():
    from routers import categories

    assert categories.router.prefix == "/api"
    assert "Categories" in categories.router.tags


def test_fixed_spec_paths_not_swallowed_by_catch_all():
    """/names, /key-source и /refresh/.../progress матчатся своими маршрутами,
    а не catch-all /specs/{platform}/{category_id:path}.

    Оба маршрута требуют авторизацию (Depends(get_current_user)), поэтому
    различаем их по 401 (сработал фиксированный маршрут: дошла до авторизации)
    против 404/405 (маршрут не найден). 401 у всех фиксированных путей
    означает, что catch-all их НЕ перехватил раньше времени.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routers import categories

    app = FastAPI()
    app.include_router(categories.router)
    client = TestClient(app, raise_server_exceptions=False)

    fixed_paths = [
        "/api/specs/ozon/names",
        "/api/specs/ozon/key-source",
        "/api/specs/ozon/refresh/some-task-id/progress",
        "/api/specs/ozon/refresh/some-task-id/events",
        "/api/admin/specs-tasks/events",
    ]
    for path in fixed_paths:
        r = client.get(path)
        assert r.status_code == 401, (
            f"GET {path} -> {r.status_code}: маршрут не зарегистрирован "
            f"или перехвачен catch-all /specs/{{platform}}/{{category_id:path}}"
        )
