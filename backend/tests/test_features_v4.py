"""
✅ v4: тесты нового функционала — массовый ТН ВЭД, профили миграции.

Только чистая логика (без БД): агрегатор кодов ТН ВЭД и валидация
pydantic-схем профилей. Undo-снапшоты покрываются tests/test_bulk_ops.py.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers.profiles import MigrationProfilePayload  # noqa: E402
from routers.tnved import BATCH_LIMIT, _aggregate_codes  # noqa: E402

# ==================== _aggregate_codes (массовый ТН ВЭД) ====================


def test_aggregate_codes_counts_and_orders():
    results = [
        {
            "product_id": 1,
            "suggestions": [
                {"code": "6109", "description": "Футболки"},
                {"code": "6110", "description": "Свитеры"},
            ],
        },
        {"product_id": 2, "suggestions": [{"code": "6109", "description": "Футболки"}]},
        {"product_id": 3, "suggestions": []},
    ]
    agg = _aggregate_codes(results)
    assert agg[0] == {"code": "6109", "description": "Футболки", "count": 2}
    assert agg[1]["count"] == 1
    assert len(agg) == 2  # пустые товары не создают записей


def test_aggregate_codes_empty():
    assert _aggregate_codes([]) == []
    assert _aggregate_codes([{"product_id": 1, "suggestions": []}]) == []


def test_aggregate_codes_capped_at_15():
    results = [
        {"product_id": i, "suggestions": [{"code": f"code{i}", "description": f"d{i}"}]}
        for i in range(20)
    ]
    assert len(_aggregate_codes(results)) == 15


# ==================== Валидация профилей миграции ====================


def test_profile_payload_ok():
    p = MigrationProfilePayload(name="  Распродажа Ozon  ", platform="OZON", vat_rate="10")
    assert p.name == "Распродажа Ozon"
    assert p.platform == "ozon"  # нормализация регистра


def test_profile_payload_empty_name_rejected():
    with pytest.raises(ValueError):
        MigrationProfilePayload(name="   ", platform="ozon")


def test_profile_payload_unknown_platform_rejected():
    with pytest.raises(ValueError):
        MigrationProfilePayload(name="Профиль", platform="notamarketplace")


def test_batch_limit_is_sane():
    assert 1 <= BATCH_LIMIT <= 1000
