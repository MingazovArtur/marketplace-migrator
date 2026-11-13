"""
Подбор целевой категории и канонических атрибутов для миграции.

Выделено из монолитного tasks.py (E-5, неделя 4); Р20 — разбиение
монолита tasks/matching.py (459 строк) на пакет по доменам (прецеденты
Р8–Р19 из docs/engineering.md):

  - _text.py  — нормализация имён (_norm_name), русский стемминг
                (_stem_ru), безопасный float (_safe_float), базовый
                источник импорта (_base_source — защита от накопления
                «A → B → B → B»)
  - _cache.py — P-3: TTL-кэш справочника спеков площадки (было: своя
                сессия БД и полная выгрузка ВСЕХ имён категорий на каждый
                вызов): _spec_cache_invalidate / _spec_cache_load /
                _spec_name_exists / _load_spec_for_category
  - _match.py — умный поиск спека по тексту (_match_spec_by_text со
                стеммингом) и единая точка выбора целевой категории
                (_pick_target_category, категория-маппер)
  - _attrs.py — конфигурация канонических атрибутов XLS-шаблона Ozon
                (CANON_ATTRS, TNVED_NAMES) и авто-дозаполнение
                обязательных атрибутов (_ensure_canonical_attributes)

Публичный API сохранён без изменений: импортёры `from tasks.matching
import ...` (tasks/catalog_tasks — _spec_cache_invalidate;
tasks/migrate_tasks/_single и _batch — _pick_target_category,
_ensure_canonical_attributes, _base_source, _safe_float;
tests/test_money_helpers.py — _base_source, _safe_float, _stem_ru)
не менялись. Точки патчинга тестов migrate_tasks — подмодули
tasks/migrate_tasks/_single и _batch (имена импортированы туда) —
стабильны.

CategoryMapper-инстанс (category_mapper в монолите) живёт в _match.py
и создаётся при первом импорте пакета — как раньше при импорте модуля.
Логгеры подмодулей — иерархические дети «tasks.matching»
(tasks.matching._text и т.д.): конфигурация логирования по имени
«tasks.matching» продолжает действовать на все подмодули.
"""

from tasks.matching._attrs import CANON_ATTRS, TNVED_NAMES, _ensure_canonical_attributes
from tasks.matching._cache import _spec_cache_invalidate
from tasks.matching._match import _pick_target_category
from tasks.matching._text import _base_source, _safe_float, _stem_ru

__all__ = [
    "_base_source",
    "_safe_float",
    "_stem_ru",
    "_spec_cache_invalidate",
    "_pick_target_category",
    "_ensure_canonical_attributes",
    "CANON_ATTRS",
    "TNVED_NAMES",
]
