"""Репозиторий товаров: CRUD, фильтрация, пагинация, массовые операции (P-2/P-3).

Dual-Engine: синхронные методы (для Celery и сервисов) + неблокирующие
методы на AsyncSession для роутеров FastAPI.

Р14 (разбиение монолита database/repository/products.py, 593 строки, на
пакет миксинов — по прецедентам Р8–Р13 из docs/engineering.md):

  - _serialize.py    — _to_dict: Product → dict (P-1: Decimal → float)
  - _filters.py      — _apply_filters / _apply_async_filters (Query/Select)
  - _async_reads.py  — get_all_async / get_by_id_async / get_stats_async
  - _sync_reads.py   — get_all / get_by_id / find_by_external / get_by_ids /
                       get_stats (синхронный контур Celery/сервисов)
  - _writes.py       — add / update / bulk_update / update_batch / delete
  - _bulk_import.py  — P-2 bulk_import: _import_payload, _variant_rows,
                       _attr_rows (статические хелперы variant_repo/attr_repo)

Финальный класс собирается в _repository.py из шести миксинов; тела методов
перенесены 1:1, порядок MRO: сериализация → фильтры → чтения → записи.

Публичный API сохранён без изменений: `from database.repository.products
import ProductRepository, repo` (импортёры database/repository/__init__.py,
variants.py, attributes.py и tests/test_money_helpers.py НЕ менялись);
статические хелперы ProductRepository._to_dict/_variant_rows/_attr_rows
доступны через наследование — обращения к ним через класс работают как
в монолите.
"""

from database.repository.products._repository import ProductRepository, repo

__all__ = [
    "ProductRepository",
    "repo",
]
