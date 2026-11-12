"""Сборка ProductRepository из доменных миксинов (Р14) + глобальный экземпляр repo.

Тела методов перенесены из монолита database/repository/products.py (593 строки)
1:1 — без переопределений и дублирования: класс только наследует шесть
миксинов, поэтому и методы экземпляра (self._to_dict, self._apply_filters),
и статические хелперы через класс (ProductRepository._variant_rows —
repository/variants.py, attributes.py, tests/test_money_helpers.py)
доступны как в монолите.
"""

from database.repository.products._async_reads import _AsyncReadsMixin
from database.repository.products._bulk_import import _BulkImportMixin
from database.repository.products._filters import _FiltersMixin
from database.repository.products._serialize import _SerializeMixin
from database.repository.products._sync_reads import _SyncReadsMixin
from database.repository.products._writes import _WritesMixin


class ProductRepository(
    _SerializeMixin,
    _FiltersMixin,
    _AsyncReadsMixin,
    _SyncReadsMixin,
    _WritesMixin,
    _BulkImportMixin,
):
    """Dual-Engine репозиторий товаров (P-2/P-3): синхронные методы для
    Celery и сервисов + неблокирующие на AsyncSession для роутеров FastAPI."""


# Глобальный экземпляр (совместимость импортов: from database.repository import repo)
repo = ProductRepository()
