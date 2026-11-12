"""
Валидатор товаров по спекам площадок (перед генерацией XLSX).

Р12 (разбиение монолита services/spec_validator.py, 618 строк, на пакет —
по прецеденту services/ozon_specs/ (Р8) и services/tnved_mapper/ (Р11)):

  - _canon.py     — агрессивная нормализация имён (_norm_name), синонимы и
                    канон обязательных атрибутов XLS-шаблона Ozon
                    (Бренд/Модель/Тип/Маркировка), CANON_LABELS,
                    OZON_TEMPLATE_REQUIRED_ORDER (канонические 13 полей)
  - _ozon_base.py — базовые колонки шаблона Ozon (эталон XLS 23.09.2026):
                    артикул/цена/НДС/ТН ВЭД/габариты/фото,
                    _is_valid_photo_url (Яндекс.Диск или JPG/PNG)
  - _attributes.py— атрибуты категории по спеку: словари, мультиселект и
                    лимиты, числа без единиц, JSON-атрибуты, хештеги
  - _entry.py     — точки входа validate_product_by_spec /
                    validate_products_by_specs (агрегаты: дубли артикулов,
                    готовность) + подакцизные категории

ВАЖНО (v3 — согласование с XLS-шаблоном): блокируют экспорт
(severity=error) ТОЛЬКО 13 канонических колонок шаблона; прочие атрибуты
спека с is_required=true дают severity=warning — XLS-шаблон пропускает
файл без них, Ozon может попросить дозаполнить в кабинете. Финальная
проверка канонов выполняется ОДИН раз в конце _validate_attributes —
защита от двойных ошибок при синонимах.

Публичный API сохранён: `from services.spec_validator import
validate_product_by_spec, validate_products_by_specs` (импортёр
routers/export/preview.py не менялся); константы EXCISABLE_CATEGORIES,
HASHTAG_RE, OKPD_RE, VALID_PHOTO_DOMAINS, VALID_PHOTO_EXT, CANON_LABELS,
OZON_TEMPLATE_REQUIRED_ORDER, TEMPLATE_REQUIRED_ATTRS_RAW — те же объекты,
что в подмодулях.
"""

from services.spec_validator._attributes import HASHTAG_RE
from services.spec_validator._canon import (
    CANON_LABELS,
    OZON_TEMPLATE_REQUIRED_ORDER,
    TEMPLATE_REQUIRED_ATTRS_RAW,
)
from services.spec_validator._entry import (
    EXCISABLE_CATEGORIES,
    validate_product_by_spec,
    validate_products_by_specs,
)
from services.spec_validator._ozon_base import (
    OKPD_RE,
    VALID_PHOTO_DOMAINS,
    VALID_PHOTO_EXT,
)

__all__ = [
    "CANON_LABELS",
    "EXCISABLE_CATEGORIES",
    "HASHTAG_RE",
    "OKPD_RE",
    "OZON_TEMPLATE_REQUIRED_ORDER",
    "TEMPLATE_REQUIRED_ATTRS_RAW",
    "VALID_PHOTO_DOMAINS",
    "VALID_PHOTO_EXT",
    "validate_product_by_spec",
    "validate_products_by_specs",
]
