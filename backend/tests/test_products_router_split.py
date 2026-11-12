"""Р10: гарантия, что разбиение routers/products.py (791 строка) на пакет
routers/products/ не потеряло маршруты и публичный API монолита.

Сверяет таблицу (path, method) с полным списком эндпоинтов монолита
(14 маршрутов) через OpenAPI-схему (served_routes) — версионно-стойко.

Отдельно фиксирует ПОРЯДОК матчинга: фиксированные GET-пути
(/products/category-counts, /products/categories-suggest, /products/edit-history)
обязаны срабатывать раньше параметрического GET /products/{product_id} —
иначе «category-counts» парсился бы как product_id и отдавал 422
(регрессия описана в docstring пакета).
"""

from _route_helpers import served_routes

EXPECTED_ROUTES = {
    ("/api/products", "GET"),
    ("/api/products/bulk-delete", "POST"),
    ("/api/products/bulk-preview", "POST"),
    ("/api/products/bulk-undo", "POST"),
    ("/api/products/bulk-update", "PUT"),
    ("/api/products/categories-suggest", "GET"),
    ("/api/products/category-counts", "GET"),
    ("/api/products/delete-all", "POST"),
    ("/api/products/edit-history", "GET"),
    ("/api/products/{product_id}", "DELETE"),
    ("/api/products/{product_id}", "GET"),
    ("/api/products/{product_id}", "PATCH"),
    ("/api/products/{product_id}/logistics", "PUT"),
    ("/api/stats", "GET"),
}


def test_products_router_routes_preserved():
    from routers import products

    actual = served_routes(products.router)

    missing = EXPECTED_ROUTES - actual
    extra = actual - EXPECTED_ROUTES
    assert not missing, f"Потеряны маршруты при разбиении пакета: {sorted(missing)}"
    assert not extra, f"Появились неожидаемые маршруты: {sorted(extra)}"


def test_products_router_prefix_and_tag():
    from routers import products

    assert products.router.prefix == "/api"
    assert "Products" in products.router.tags


def test_public_api_preserved():
    """Все публичные имена монолита остались на пакете — те же объекты,
    что в подмодулях (импортёр main.py и тесты используют атрибутный
    доступ, импортеры не менялись)."""
    import routers.products as products
    from database import repository
    from routers.products import _bulk, _delete, _lists, _single, _support

    # эндпоинты — те же объекты, что в подмодулях
    assert products.bulk_update_products is _bulk.bulk_update_products
    assert products.bulk_preview_products is _bulk.bulk_preview_products
    assert products.bulk_undo_products is _bulk.bulk_undo_products
    assert products.get_edit_history is _bulk.get_edit_history
    assert products.products_category_counts is _lists.products_category_counts
    assert products.categories_suggest is _lists.categories_suggest
    assert products.get_products is _lists.get_products
    assert products.get_stats is _lists.get_stats
    assert products.update_product is _single.update_product
    assert products.update_product_logistics is _single.update_product_logistics
    assert products.get_product_by_id is _single.get_product_by_id
    assert products.delete_product is _single.delete_product
    assert products.bulk_delete_products is _delete.bulk_delete_products
    assert products.delete_all_products is _delete.delete_all_products

    # схемы и константы — из _support
    assert products.BulkDeleteRequest is _support.BulkDeleteRequest
    assert products.DeleteAllRequest is _support.DeleteAllRequest
    assert products.ProductUpdateRequest is _support.ProductUpdateRequest
    assert products.UndoRequest is _support.UndoRequest
    assert products.SORT_MAP is _support.SORT_MAP
    assert products.SNAPSHOTS_PER_USER is _support.SNAPSHOTS_PER_USER

    # точки патчинга тестов — модули database.repository, те же объекты,
    # что используют подмодули (test_products_api.py подменяет products.repo)
    assert products.repo is repository.repo
    assert products.stats_repo is repository.stats_repo
    assert _single.repo is repository.repo
    assert _bulk.stats_repo is repository.stats_repo
    assert _delete.stats_repo is repository.stats_repo

    # на пакете нет случайных публичных имён (полный каталог поверхности)
    public = {n for n in dir(products) if not n.startswith("_")}
    assert public == {
        "APIRouter",
        "SNAPSHOTS_PER_USER",
        "SORT_MAP",
        "BulkDeleteRequest",
        "DeleteAllRequest",
        "ProductUpdateRequest",
        "UndoRequest",
        "bulk_delete_products",
        "bulk_preview_products",
        "bulk_undo_products",
        "bulk_router",
        "bulk_update_products",
        "categories_suggest",
        "delete_all_products",
        "delete_product",
        "delete_router",
        "get_edit_history",
        "get_product_by_id",
        "get_products",
        "get_stats",
        "lists_router",
        "products_category_counts",
        "repo",
        "router",
        "single_router",
        "stats_repo",
        "update_product",
        "update_product_logistics",
    }


def test_fixed_get_paths_not_swallowed_by_parametric():
    """Фиксированные GET-пути матчатся своими маршрутами, а не параметрическим
    GET /products/{product_id} из _single.

    Авторизация и БД подменяются: если путь перехвачен параметрическим
    маршрутом, product_id='category-counts' не проходит int-валидацию → 422;
    правильный маршрут доходит до эндпоинта (на фейковой БД) и отвечает
    не-422. Порядок include_router в пакете — MATERIALEN (см. docstring
    пакета routers/products/__init__.py).
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from core.auth import get_current_user
    from database.models import User
    from database.session import get_async_db
    from routers import products

    app = FastAPI()
    app.include_router(products.router)

    user = User(id=7, username="u7", email="u7@x.io", role="user", is_active=True)

    class _Rows:
        def all(self):
            return []

        def scalars(self):
            return self

    class _FakeDB:
        async def execute(self, *args, **kwargs):
            return _Rows()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_async_db] = lambda: _FakeDB()

    client = TestClient(app, raise_server_exceptions=False)
    for path in (
        "/api/products/category-counts",
        "/api/products/categories-suggest",
        "/api/products/edit-history",
    ):
        r = client.get(path)
        assert r.status_code != 422, (
            f"GET {path} -> {r.status_code}: путь перехвачен параметрическим "
            f"GET /products/{{product_id}} — порядок include_router в пакете сломан"
        )
