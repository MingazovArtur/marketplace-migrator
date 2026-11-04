"""
Генератор XLSX v2: файлы, СТРУКТУРНО идентичные реальным шаблонам Ozon и Яндекс Маркета.

✅ v9 (приоритет эталонных шаблонов для ВСЕХ площадок):
  - Если для площадки (Яндекс Маркет, Ozon, Wildberries, Магнит) загружен эталонный
    шаблон в разделе «Шаблоны», выгрузка собирается напрямую в оригинальном файле
    площадки через fill_official_template (удаляется строка-пример и дописываются товары).
  - Если эталон ещё не загружен — используется резервная генерация книги по структуре площадки.

E-7 (неделя 4): монолит xlsx_generator.py (1455 строк) разбит на пакет:
  - columns — константы структуры и стили
  - common — общие хелперы
  - yandex / ozon / simple — билдеры книг по площадкам
  - generate_export (здесь) — точка входа с приоритетом эталонных шаблонов

Публичный API сохранён: `from services.xlsx_generator import generate_export`.
"""

import io
import zipfile

from services.xlsx_generator.common import _slug
from services.xlsx_generator.ozon import build_ozon_workbook
from services.xlsx_generator.simple import build_simple_workbook
from services.xlsx_generator.yandex import build_yandex_workbook

__all__ = [
    "generate_export",
    "build_yandex_workbook",
    "build_ozon_workbook",
    "build_simple_workbook",
]


def generate_export(products: list, specs_by_category: dict, platform: str):
    """
    Возвращает (bytes, filename).
    ✅ Приоритет 1: эталонный шаблон площадки (Яндекс Маркет, Ozon, WB, Магнит),
       загруженный в разделе «Шаблоны» — открывается как каркас, зачищается пример
       и заполняется товарами (формат 1:1 с кабинетом площадки).
    ✅ Приоритет 2 (если эталон не загружен): генерация книги по структуре площадки.
    """
    from services.template_filler import fill_official_template, has_official_template

    # Яндекс Маркет принимает все товары разных категорий на одном листе «Список товаров»
    if platform == "yandex":
        first_cat = (
            (products[0].get("mapped_category") or products[0].get("category") or "")
            if products
            else ""
        )
        if has_official_template(first_cat, platform="yandex"):
            data = fill_official_template(first_cat, products, spec=None, platform="yandex")
            return data, "yandex_market_assortment.xlsx"

        wb = build_yandex_workbook(products)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), "yandex_market_assortment.xlsx"

    groups = {}
    for p in products:
        cat = p.get("mapped_category") or p.get("category") or "Без категории"
        groups.setdefault(cat, []).append(p)

    files = []
    for cat, prods in groups.items():
        if has_official_template(cat, platform=platform):
            files.append(
                (
                    f"{platform}_{_slug(cat)}",
                    fill_official_template(
                        cat, prods, specs_by_category.get(cat), platform=platform
                    ),
                )
            )
            continue
        spec = specs_by_category.get(cat)
        wb = (
            build_ozon_workbook(prods, spec)
            if platform == "ozon"
            else build_simple_workbook(platform, prods, spec)
        )
        buf = io.BytesIO()
        wb.save(buf)
        files.append((f"{platform}_{_slug(cat)}", buf.getvalue()))

    if len(files) == 1:
        return files[0][1], f"{files[0][0]}.xlsx"

    zipbuf = io.BytesIO()
    with zipfile.ZipFile(zipbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(f"{name}.xlsx", data)
    return zipbuf.getvalue(), f"{platform}_export_{len(files)}_categories.zip"
