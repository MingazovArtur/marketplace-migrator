"""R35 (В-14): согласованность реестра платформ.

Enum Platform, PLATFORM_CONFIG и PRICE_RULES обязаны иметь одинаковые
ключи: раньше /api/platforms делал PLATFORM_CONFIG[p.value] и падал бы
с KeyError при любом расхождении enum и реестра. Тест ловит рассинхрон
заранее, а не на первом запросе клиента.
"""

import pytest
from fastapi.testclient import TestClient

from core.platforms import PLATFORM_CONFIG, PRICE_RULES, Platform
from main import app


def test_registry_keys_in_sync():
    """Enum, конфиг и ценовые правила — один и тот же набор площадок."""
    enum_values = set(Platform.all_values())
    assert enum_values == set(PLATFORM_CONFIG), "Platform и PLATFORM_CONFIG разошлись"
    assert enum_values == set(PRICE_RULES), "Platform и PRICE_RULES разошлись"


def test_config_fields_present():
    """У каждой площадки есть обязательные поля реестра (name, color)."""
    for key, cfg in PLATFORM_CONFIG.items():
        assert cfg.get("name"), f"{key}: нет name"
        assert cfg.get("color"), f"{key}: нет color"


@pytest.fixture
def no_bans(monkeypatch):
    """Redis в тестах недоступен: баны не проверяем, лимитер выключаем
    (SlowAPIMiddleware при enabled=False пропускает запросы мимо storage)."""
    monkeypatch.setattr("main.is_banned", lambda identifier: False)
    from core.rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


def test_platforms_endpoint_lists_all(no_bans):
    """/api/platforms отдаёт все площадки и не падает на расхождении."""
    client = TestClient(app)
    resp = client.get("/api/platforms")
    assert resp.status_code == 200
    body = resp.json()["platforms"]
    assert {p["id"] for p in body} == set(Platform.all_values())
    assert all(p["name"] and p["color"] for p in body)
