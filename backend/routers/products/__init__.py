"""
Роутер товаров: список/фильтрация/пагинация, массовые правки с undo,
массовое удаление, точечная правка и логистика.

Р10 (разбиение монолита routers/products.py, 791 строка, на пакет — по
прецеденту routers/export/ (Р1) и routers/categories/ (Р7)):

  - _support.py  — схемы запросов (bulk-delete/delete-all/правка/undo),
                   SORT_MAP, SNAPSHOTS_PER_USER, валидация категории по спекам
  - _bulk.py     — массовые правки: bulk-update/bulk-preview/bulk-undo +
                   лента edit-history (undo-снапшоты через services/edit_history)
  - _lists.py    — чтение: список с фильтрами/сортировкой/пагинацией, /stats,
                   счётчики категорий (О3), подсказки категорий из спеков
  - _single.py   — одиночный товар: правка (PATCH), логистика
                   (PUT /{id}/logistics), чтение (GET), удаление (DELETE)
  - _delete.py   — массовое удаление: bulk-delete (один bulk DELETE, P-5)
                   и delete-all (с confirm)

Публичный API сохранён: `from routers import products; products.router`
(main.py не менялся); схемы, константы, эндпоинты и точки патчинга тестов
(repo/stats_repo — модули database.repository) остались на пакете теми же
объектами, что в подмодулях.

ВАЖНО — порядок include_router ниже: параметрические маршруты
GET/PATCH/DELETE /products/{product_id} (модуль _single) регистрируются
ПОСЛЕ модулей _bulk и _lists, где объявлены фиксированные GET-пути
/products/edit-history, /products/category-counts и
/products/categories-suggest — иначе «category-counts» парсился бы как
product_id и отдавал 422 (тест
test_fixed_get_paths_not_swallowed_by_parametric).
"""

from fastapi import APIRouter

from routers.products._bulk import router as bulk_router
from routers.products._delete import router as delete_router
from routers.products._lists import router as lists_router
from routers.products._single import router as single_router
from routers.products._support import (
    SNAPSHOTS_PER_USER,
    SORT_MAP,
    BulkDeleteRequest,
    DeleteAllRequest,
    ProductUpdateRequest,
    UndoRequest,
)

router = APIRouter(prefix="/api", tags=["Products"])
router.include_router(bulk_router)
router.include_router(lists_router)
router.include_router(single_router)
router.include_router(delete_router)

# Публичные имена монолита для импортёров и тестов (точки патчинга:
# tests/test_products_api.py подменяет products.repo — это модуль
# database.repository, тот же объект, что в подмодулях пакета).
from database.repository import repo, stats_repo  # noqa: E402
from routers.products._bulk import (  # noqa: E402
    bulk_preview_products,
    bulk_undo_products,
    bulk_update_products,
    get_edit_history,
)
from routers.products._delete import (  # noqa: E402
    bulk_delete_products,
    delete_all_products,
)
from routers.products._lists import (  # noqa: E402
    categories_suggest,
    get_products,
    get_stats,
    products_category_counts,
)
from routers.products._single import (  # noqa: E402
    delete_product,
    get_product_by_id,
    update_product,
    update_product_logistics,
)

__all__ = [
    "router",
    # _support: схемы и константы
    "SNAPSHOTS_PER_USER",
    "SORT_MAP",
    "BulkDeleteRequest",
    "DeleteAllRequest",
    "ProductUpdateRequest",
    "UndoRequest",
    # точки патчинга тестов (модули database.repository)
    "repo",
    "stats_repo",
    # _bulk / _delete / _lists / _single: эндпоинты монолита
    "bulk_preview_products",
    "bulk_undo_products",
    "bulk_update_products",
    "get_edit_history",
    "bulk_delete_products",
    "delete_all_products",
    "categories_suggest",
    "get_products",
    "get_stats",
    "products_category_counts",
    "delete_product",
    "get_product_by_id",
    "update_product",
    "update_product_logistics",
]
