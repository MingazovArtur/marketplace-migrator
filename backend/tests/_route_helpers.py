"""Общие хелперы тестов роутеров.

served_routes(): множество (path, method), которые FastAPI РЕАЛЬНО обслуживает
для роутера, — через OpenAPI-схему собранного приложения.

Не наивный обход router.routes: в Starlette >= 1.10 include_router
оборачивает вложенные роутеры в объекты _IncludedRouter (без methods), и
плоский обход видел «пустой» роутер. OpenAPI показывает ровно то, что
сервится, в любой версии FastAPI/Starlette.
"""

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def served_routes(router) -> set[tuple[str, str]]:
    """Множество (path, method), которые FastAPI реально обслуживает для роутера."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    return {
        (path, method.upper())
        for path, ops in schema.get("paths", {}).items()
        for method in ops
        if method.lower() in _HTTP_METHODS
    }
