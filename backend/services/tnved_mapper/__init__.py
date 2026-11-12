"""
Сервис для авто-подбора кодов ТН ВЭД ЕАЭС на основе названия и категории
товара. Расширенный справочник для селлеров маркетплейсов (на основе ЕТТ ЕАЭС).

Р11 (разбиение монолита services/tnved_mapper.py, 694 строки, на пакет):

  - _database_a.py — справочник, часть 1 (одежда/обувь, электроника, дом и
                     кухня, косметика, детские товары, спорт, авто, инструменты)
  - _database_b.py — справочник, часть 2 (канцелярия, творчество, животные,
                     продукты, бытовая химия, стройка, медицина)
  - _database.py   — склейка TNVED_DATABASE = {**A, **B} (порядок МАТЕРИАЛЕН)
  - _lookup.py     — поиск: suggest_tnved / get_tnved_description / search_tnved

Публичный API сохранён: `from services.tnved_mapper import suggest_tnved,
get_tnved_description, search_tnved, TNVED_DATABASE` (импортёр
routers/tnved.py не менялся).

ВАЖНО — порядок ключей справочника: search_tnved возвращает первые 10
совпадений В ПОРЯДКЕ справочника, suggest_tnved при равном score сохраняет
порядок справочника. Справочник разбит на части последовательными строками
(часть A — до секции «Канцелярия и офис», часть B — после), склейка
{**A, **B} воспроизводит порядок и значения монолита байт-в-байт:
позиция дублированного ключа — из A, значение — из B. Контракт описан в
_database.py и зафиксирован тестом test_key_order_and_cross_values.
"""

from services.tnved_mapper._database import TNVED_DATABASE
from services.tnved_mapper._lookup import (
    get_tnved_description,
    search_tnved,
    suggest_tnved,
)

__all__ = [
    "TNVED_DATABASE",
    "suggest_tnved",
    "get_tnved_description",
    "search_tnved",
]
