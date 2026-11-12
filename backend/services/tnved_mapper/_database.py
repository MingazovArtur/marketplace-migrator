"""Склейка полного справочника ТН ВЭД из двух частей.

Части (_database_a/_database_b) — последовательные строки монолита
services/tnved_mapper.py (Р11); склейка ниже воспроизводит его байт-в-байт:

  - порядок ключей: сначала все ключи части A, затем новые ключи части B;
  - для ключей, продублированных в обеих частях (11 сквозных дублей),
    ПОЗИЦИЯ берётся из A (первое вхождение в литерале монолита),
    а ЗНАЧЕНИЕ — из B (последний литерал побеждал и в монолите).

Порядок итерации МАТЕРИАЛЕН: search_tnved возвращает первые 10 совпадений
в порядке справочника, suggest_tnved при равном score сохраняет порядок
справочника. Зафиксировано тестом test_key_order_and_cross_values
(tests/test_tnved_mapper_split.py).
"""

from services.tnved_mapper._database_a import TNVED_DATABASE_A
from services.tnved_mapper._database_b import TNVED_DATABASE_B

TNVED_DATABASE = {**TNVED_DATABASE_A, **TNVED_DATABASE_B}
