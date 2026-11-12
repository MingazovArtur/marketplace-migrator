"""
Сервис для работы со справочниками категорий маркетплейсов.

Поддерживает два режима работы:
1. Встроенные справочники (заглушки) — работают без API-ключей
2. Реальные API — при передаче валидного ключа загружаются актуальные данные

Р6 (разбиение монолита services/category_service.py, 709 строк, на пакет —
по прецеденту template_filler/ из docs/engineering.md):

  - _mocks.py       — встроенные справочники-заглушки (данные)
  - _api_loaders.py — загрузка категорий из реальных API (Ozon/WB/Яндекс)
  - _storage.py     — SQLAlchemy-операции: категории и маппинги
  - _service.py     — класс CategoryService (кэш→БД→API→заглушки) и синглтон

Публичный API сохранён без изменений: `from services.category_service
import category_service` (импортёры routers/, tasks/ не менялись).
"""

from services.category_service._service import CategoryService, category_service

__all__ = ["CategoryService", "category_service"]
