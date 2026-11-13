"""Тесты UX-раунда 2 (свежие данные для модалок + счётчик товаров с пропусками).

Стиль проекта: чистые юнит-тесты без сети и БД — репозиторий подменяется
стабами через monkeypatch.

Покрывает:
  - GET /api/products/{id}: возвращает товар из БД, а не из фронтового кэша
    (баг «в окне миграции цена 0 после Заполнить пропуски»);
  - 404 для чужого/несуществующего товара;
  - админу отдаётся любой товар (is_admin=True уходит в репозиторий);
  - compute_gaps: products_with_gaps — у скольких товаров есть хотя бы
    один пропуск (total раньше выдавали за это число).
"""

import pytest
from fastapi import HTTPException

import routers.products as products_router
import services.defaults_service as defaults_service
from database.models import User

# ---------------------------------------------------------------------------
# Стабы
# ---------------------------------------------------------------------------


def make_user(uid=7, role="user"):
    return User(id=uid, username=f"u{uid}", email=f"u{uid}@x.io", role=role, is_active=True)


class FakeProduct:
    """Товар с любыми полями: compute_gaps читает только атрибуты."""

    def __init__(self, **kw):
        self.photos = kw.pop("photos", [])
        self.price = None
        self.vat_rate = None
        self.okpd_code = None
        self.package_weight_grams = None
        self.package_width_mm = None
        self.package_height_mm = None
        self.package_length_mm = None
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeQuery:
    def __init__(self, items):
        self._items = items

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._items


class _FakeSession:
    def __init__(self, items):
        self._items = items

    def query(self, *args, **kwargs):
        return _FakeQuery(self._items)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# GET /api/products/{product_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_product_by_id_returns_fresh_data(monkeypatch):
    """Модалка миграции получает СВЕЖУЮ цену из БД (не 0 из старого кэша)."""

    async def fake_get(db, product_id, user_id=None, is_admin=False):
        assert product_id == 384
        assert user_id == 7
        assert is_admin is False
        return {
            "id": 384,
            "name": "Футболка для девочек",
            "price": 99.97,
            "mapped_category": "Одежда / Футболка",
            "photos": ["http://x/1.jpg"],
        }

    monkeypatch.setattr(products_router.repo, "get_by_id_async", fake_get)
    data = await products_router.get_product_by_id(384, current_user=make_user(), db=None)
    assert data["price"] == 99.97
    assert data["id"] == 384


@pytest.mark.asyncio
async def test_get_product_by_id_admin_sees_any(monkeypatch):
    """Админу is_admin=True — репозиторий не фильтрует по владельцу."""

    seen = {}

    async def fake_get(db, product_id, user_id=None, is_admin=False):
        seen["is_admin"] = is_admin
        return {"id": product_id, "price": 0}

    monkeypatch.setattr(products_router.repo, "get_by_id_async", fake_get)
    await products_router.get_product_by_id(1, current_user=make_user(role="admin"), db=None)
    assert seen["is_admin"] is True


@pytest.mark.asyncio
async def test_get_product_by_id_404(monkeypatch):
    """Чужой или несуществующий товар → 404, без раскрытия деталей."""

    async def fake_get(db, product_id, user_id=None, is_admin=False):
        return None

    monkeypatch.setattr(products_router.repo, "get_by_id_async", fake_get)
    with pytest.raises(HTTPException) as exc:
        await products_router.get_product_by_id(999, current_user=make_user(), db=None)
    assert exc.value.status_code == 404
    assert "не найден" in exc.value.detail


# ---------------------------------------------------------------------------
# compute_gaps: products_with_gaps
# ---------------------------------------------------------------------------


def _full(**extra):
    base = {
        "price": 100,
        "vat_rate": "20",
        "okpd_code": "6109100010",
        "package_weight_grams": 100,
        "package_width_mm": 200,
        "package_height_mm": 30,
        "package_length_mm": 250,
        "photos": ["http://x/1.jpg"],
    }
    base.update(extra)
    return FakeProduct(**base)


def test_compute_gaps_counts_products_with_gaps(monkeypatch):
    """products_with_gaps — только товары с реальными пропусками, не total."""
    items = [
        _full(),  # готов к выгрузке
        _full(price=0),  # только цена
        _full(vat_rate=None, okpd_code=None, package_weight_grams=0),  # три поля сразу
        _full(photos=[]),  # нет фото
    ]
    monkeypatch.setattr(defaults_service, "SessionLocal", lambda: _FakeSession(items))

    res = defaults_service.compute_gaps(user_id=1, status="all")

    assert res["total"] == 4
    assert res["products_with_gaps"] == 3  # готовый товар не считается
    assert res["gaps"]["price"] == 1
    assert res["gaps"]["vat_rate"] == 1
    assert res["gaps"]["okpd_code"] == 1
    assert res["gaps"]["package_weight_grams"] == 1
    assert res["gaps"]["main_photo"] == 1


def test_compute_gaps_all_ready(monkeypatch):
    """Все товары готовы — products_with_gaps = 0, все счётчики по нулям."""
    items = [_full(), _full(price=1)]
    monkeypatch.setattr(defaults_service, "SessionLocal", lambda: _FakeSession(items))

    res = defaults_service.compute_gaps(user_id=1, status="all")

    assert res["total"] == 2
    assert res["products_with_gaps"] == 0
    assert all(n == 0 for n in res["gaps"].values())
