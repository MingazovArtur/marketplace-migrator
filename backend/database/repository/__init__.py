"""
Репозитории для работы с БД: товары, журнал операций, характеристики, вариации, статистика.

E-6 (неделя 4): монолит database/repository.py (1087 строк) разбит на пакет
модулей по доменам. Публичный API сохранён 1:1 — `from database.repository
import repo, op_log, attr_repo, variant_repo, stats_repo` работает как раньше
(10 файлов-импортёров не менялись).

Схему БД ведёт ТОЛЬКО Alembic (create_all не вызываем).

Модули:
  - products        — ProductRepository (CRUD, фильтры, bulk-операции P-2/P-3)
  - operation_logs  — OperationLogRepository (журнал файлов и миграций)
  - attributes      — AttributeRepository (характеристики)
  - variants        — VariantRepository (вариации)
  - stats           — StatsRepository (запись и агрегация статистики)
"""

from database.repository.attributes import AttributeRepository, attr_repo
from database.repository.operation_logs import OperationLogRepository, op_log
from database.repository.products import ProductRepository, repo
from database.repository.stats import StatsRepository, stats_repo
from database.repository.variants import VariantRepository, variant_repo

__all__ = [
    "ProductRepository",
    "OperationLogRepository",
    "AttributeRepository",
    "VariantRepository",
    "StatsRepository",
    "repo",
    "op_log",
    "attr_repo",
    "variant_repo",
    "stats_repo",
]
