"""Р6: гарантия, что разбиение services/category_service.py на пакет
сохранило публичный API и поведение.

Импортёры (routers/, tasks/) используют `from services.category_service
import category_service` — синглтон должен быть доступен как и раньше.
Хелперы (заглушки, API-загрузчики, хранение) — чистые функции, проверяем
их поведение без БД (monkeypatch).
"""


def test_public_api_preserved():
    from services.category_service import CategoryService, category_service

    assert isinstance(category_service, CategoryService)

    methods = {m for m in dir(category_service) if not m.startswith("_")}
    assert methods == {
        "get_categories",
        "get_categories_with_api_key",
        "get_category_mapping",
        "get_mapping_for_product",
        "save_category_mapping",
    }


def test_mock_categories_data():
    """Заглушки: непустые справочники для трёх площадок, одинаковая схема записей."""
    from services.category_service._mocks import get_mock_categories

    required_keys = {"id", "name", "parent_id", "full_path", "level"}
    for platform in ("ozon", "wildberries", "yandex"):
        cats = get_mock_categories(platform)
        assert cats, f"пустой справочник-заглушка для {platform}"
        for cat in cats:
            assert required_keys <= set(cat.keys()), f"нет полей в {platform}: {cat}"

    assert get_mock_categories("unknown-platform") == []


def test_load_categories_from_api_unknown_platform():
    """Неизвестная площадка — None (фолбэк на заглушки делает вызывающий)."""
    from services.category_service._api_loaders import load_categories_from_api

    assert load_categories_from_api("unknown", "some-key") is None
    assert load_categories_from_api("ozon", "") is None


def test_ozon_loader_parses_response(monkeypatch):
    """Парсер ответа Ozon: строки-идентификаторы, disabled-категории отбрасываются."""
    from services.category_service import _api_loaders

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "result": [
                    {"id": 100, "name": "Электроника", "parent_id": 0},
                    {"id": 101, "name": "Смартфоны", "parent_id": 100},
                    {"id": 999, "name": "Скрытая", "parent_id": 0, "disabled": True},
                ]
            }

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return FakeResponse()

    monkeypatch.setattr(_api_loaders.httpx, "post", fake_post)

    result = _api_loaders._load_ozon_categories("123:secret")

    assert captured["url"] == "https://api-seller.ozon.ru/v1/description-category/tree"
    assert captured["headers"]["Client-Id"] == "123"
    assert captured["headers"]["Api-Key"] == "secret"
    assert result == [
        {
            "id": "100",
            "name": "Электроника",
            "parent_id": None,  # parent_id=0 -> None
            "full_path": None,
            "level": 0,
        },
        {
            "id": "101",
            "name": "Смартфоны",
            "parent_id": "100",
            "full_path": None,
            "level": 0,
        },
    ]
    # disabled=True -> категория отброшена
    assert all(c["id"] != "999" for c in result)


def test_get_categories_falls_back_to_mocks(monkeypatch):
    """Пустая БД -> get_categories возвращает заглушки и кладёт их в кэш."""
    from services.category_service import _service
    from services.category_service._service import CategoryService

    monkeypatch.setattr(_service, "load_categories_from_db", lambda platform: [])
    saved = []
    monkeypatch.setattr(_service, "save_categories_to_db", lambda p, cats: saved.append((p, cats)))

    svc = CategoryService()
    result = svc.get_categories("ozon")

    assert result, "должны вернуться заглушки при пустой БД"
    assert saved and saved[0][0] == "ozon", "заглушки должны сохраняться в БД"
    # второй вызов — из кэша в памяти (те же данные, без повторного сохранения)
    again = svc.get_categories("ozon")
    assert again == result
    assert len(saved) == 1


def test_get_categories_with_api_key_error_falls_back(monkeypatch):
    """Ошибка API -> автоматический фолбэк на get_categories (заглушки)."""
    import httpx

    from services.category_service import _service
    from services.category_service._service import CategoryService

    def boom(platform, api_key):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(_service, "load_categories_from_api", boom)
    monkeypatch.setattr(_service, "load_categories_from_db", lambda platform: [])
    monkeypatch.setattr(_service, "save_categories_to_db", lambda p, cats: None)

    svc = CategoryService()
    result = svc.get_categories_with_api_key("ozon", "123:secret")
    assert result, "фолбэк на заглушки при сетевой ошибке API"
