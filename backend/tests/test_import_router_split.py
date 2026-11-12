"""Р13: гарантия, что разбиение routers/import_router.py (612 строк) на пакет
routers/import_router/ не потеряло маршруты и публичный API монолита.

Сверяет таблицу (path, method) с полным списком эндпоинтов монолита
(3 маршрута) через OpenAPI-схему (served_routes) — версионно-стойко.
Все 3 маршрута фиксированные (параметрических нет), порядок include_router
на матчинг не влияет — сохранён как в монолите (preview, import, file).

Семантические тесты (без слова `package`) прогонялись на монолите ДО
разбиения — так зафиксирована эквивалентность переноса (перенос узлов
дополнительно проверен по ast.dump). Тесты со словом `package`
проверяют структуру пакета и приватные хелперы через импорт
подмодулей (приватные имена на корне пакета не реэкспортируются).
"""

from _route_helpers import served_routes

EXPECTED_ROUTES = {
    ("/api/import", "POST"),
    ("/api/import/file", "POST"),
    ("/api/import/preview", "POST"),
}


def test_import_router_routes_preserved():
    from routers import import_router

    actual = served_routes(import_router.router)
    missing = EXPECTED_ROUTES - actual
    extra = actual - EXPECTED_ROUTES
    assert not missing, f"Потеряны маршруты при разбиении пакета: {sorted(missing)}"
    assert not extra, f"Появились неожидаемые маршруты: {sorted(extra)}"


def test_import_router_prefix_and_tag():
    from routers import import_router

    assert import_router.router.prefix == "/api"
    assert "Import" in import_router.router.tags


def test_import_request_get_key_variants():
    """Единая точка получения ключа: поддерживает все варианты полей фронта."""
    from routers.import_router import ImportRequest

    assert ImportRequest(key=" k1 ").get_key() == "k1"
    assert ImportRequest(key="", full_key="k2").get_key() == "k2"
    assert ImportRequest(auth_key="k3").get_key() == "k3"
    # приоритет: key → full_key → auth_key
    assert ImportRequest(key="a", full_key="b", auth_key="c").get_key() == "a"
    assert ImportRequest().get_key() == ""


def test_package_source_label_uses_platform_name():
    from routers.import_router._support import _source_label

    assert _source_label("ozon") == "Ozon (Файл)"
    assert _source_label("yandex") == "Яндекс Маркет (Файл)"
    # неизвестная платформа — ключ как есть
    assert _source_label("unknown-platform") == "unknown-platform (Файл)"


def test_max_import_file_size_constant():
    from routers.import_router import MAX_IMPORT_FILE_SIZE

    assert MAX_IMPORT_FILE_SIZE == 15 * 1024 * 1024


def test_package_parse_yandex_api_credentials(monkeypatch):
    from routers.import_router._support import _parse_yandex_api_credentials

    monkeypatch.delenv("YANDEX_BUSINESS_ID", raising=False)
    # префикс 'yandex:' отрезается
    assert _parse_yandex_api_credentials("yandex:217055223:ACMA:abc") == ("217055223", "ACMA:abc")
    assert _parse_yandex_api_credentials("217055223:ACMA:abc") == ("217055223", "ACMA:abc")
    # без business_id — дефолт из env (217055223)
    assert _parse_yandex_api_credentials("ACMA:abc") == ("217055223", "ACMA:abc")
    assert _parse_yandex_api_credentials("yandex:y0_token") == ("217055223", "y0_token")
    # '<business_id>:<длинный токен>'
    assert _parse_yandex_api_credentials("123456:abcdefghijklmnop") == ("123456", "abcdefghijklmnop")
    # не яндекс-ключ
    assert _parse_yandex_api_credentials("38146098:test") is None
    assert _parse_yandex_api_credentials("some_random_key") is None

    # кастомный business_id из env
    monkeypatch.setenv("YANDEX_BUSINESS_ID", "999")
    assert _parse_yandex_api_credentials("ACMA:abc") == ("999", "ACMA:abc")
    # пустой env и ключ без business_id — ValueError с подсказкой
    monkeypatch.setenv("YANDEX_BUSINESS_ID", "  ")
    try:
        _parse_yandex_api_credentials("ACMA:abc")
        raise AssertionError("ожидался ValueError для пустого YANDEX_BUSINESS_ID")
    except ValueError as e:
        assert "businessId" in str(e)


def test_package_public_api_preserved():
    """Все публичные имена монолита остались на пакете — те же объекты,
    что в подмодулях (импортёр main.py использует атрибутный доступ,
    не менялся)."""
    import routers.import_router as ir
    from database import repository
    from routers.import_router import _file_import, _key_import, _preview, _support

    # эндпоинты — те же объекты, что в подмодулях
    assert ir.preview_import is _preview.preview_import
    assert ir.import_products is _key_import.import_products
    assert ir.import_from_file is _file_import.import_from_file

    # схемы и константы — из _support
    assert ir.ImportRequest is _support.ImportRequest
    assert ir.MAX_IMPORT_FILE_SIZE is _support.MAX_IMPORT_FILE_SIZE

    # точки патчинга — модули database.repository, те же объекты,
    # что используют подмодули
    assert ir.repo is repository.repo
    assert ir.op_log is repository.op_log
    assert ir.stats_repo is repository.stats_repo
    assert _support.repo is repository.repo
    assert _key_import.op_log is repository.op_log
    assert _key_import.stats_repo is repository.stats_repo
    assert _file_import.op_log is repository.op_log
    assert _file_import.stats_repo is repository.stats_repo

    # на пакете нет случайных публичных имён (полный каталог поверхности)
    public = {n for n in dir(ir) if not n.startswith("_")}
    assert public == {
        "APIRouter",
        "ImportRequest",
        "MAX_IMPORT_FILE_SIZE",
        "file_import_router",
        "import_from_file",
        "import_products",
        "key_import_router",
        "op_log",
        "preview_import",
        "preview_router",
        "repo",
        "router",
        "stats_repo",
    }
