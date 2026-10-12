"""
Роутер для генерации шаблонов Excel файлов
"""

import io
import logging

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.platforms import PLATFORM_CONFIG, Platform

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Templates"])


@router.get("/templates/{platform}")
def download_template(platform: str):
    """
    Скачать шаблон Excel файла для импорта товаров

    Args:
        platform: ozon, wildberries, yandex

    Returns:
        Excel файл с шаблоном и инструкцией
    """
    platform = platform.lower()

    if platform not in Platform.all_values():
        raise HTTPException(
            status_code=404,
            detail=f"Платформа '{platform}' не найдена. Доступные: {Platform.all_values()}",
        )

    # Определяем структуру шаблона для каждой платформы
    templates = {
        "magnit": {
            "Артикул продавца": "MM-100500",
            "Название товара": "Футболка хлопковая мужская, р-р S-XXL",
            "Цена, руб": 990,
            "Остаток": 25,
            "Категория": "Одежда > Футболки",
            "Ссылка на фото": "https://example.com/tshirt.jpg",
            "Описание": "Футболка из 100% хлопка. Размеры S, M, L, XL, XXL.",
        },
        Platform.OZON: {
            "Название товара": "Смартфон Xiaomi Redmi Note 12 4/128GB",
            "Цена": 12990,
            "Артикул": "XM-RN12-128",
            "Описание": "Отличный смартфон с хорошей камерой и мощным процессором. Диагональ экрана 6.67 дюйма.",
            "Фото (URL)": "https://example.com/photo1.jpg, https://example.com/photo2.jpg",
            "Категория": "Электроника > Смартфоны",
            "Количество фото": 5,
        },
        Platform.WILDBERRIES: {
            "Наименование": "Платье летнее женское",
            "Цена с учетом скидок": 2500,
            "Баркод": "WB-12345678",
            "Описание": "Лёгкое летнее платье из натурального хлопка. Размер 44-46.",
            "Ссылка на фото": "https://example.com/dress.jpg",
            "Категория": "Одежда > Платья",
            "Бренд": "Fashion Brand",
        },
        Platform.YANDEX: {
            "Название": "Наушники беспроводные Sony WH-1000XM4",
            "Стоимость": 24990,
            "Артикул": "SONY-WH1000XM4",
            "Описание": "Премиальные беспроводные наушники с шумоподавлением.",
            "URL картинки": "https://example.com/headphones.jpg",
            "Категория": "Электроника > Аудио > Наушники",
            "Производитель": "Sony",
        },
    }

    template_data = templates.get(platform)
    platform_name = PLATFORM_CONFIG[platform]["name"]

    # Создаем DataFrame с примером и пустой строкой для заполнения
    df_example = pd.DataFrame([template_data])
    df_empty = pd.DataFrame([dict.fromkeys(template_data.keys(), "")])

    # Объединяем пример и пустую строку
    df_template = pd.concat([df_example, df_empty], ignore_index=True)

    # Записываем в буфер
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Лист 1: Шаблон
        df_template.to_excel(writer, index=False, sheet_name="Шаблон")

        # Форматируем ширину колонок
        worksheet = writer.sheets["Шаблон"]
        worksheet.column_dimensions["A"].width = 35
        worksheet.column_dimensions["B"].width = 15
        worksheet.column_dimensions["C"].width = 20
        worksheet.column_dimensions["D"].width = 50
        worksheet.column_dimensions["E"].width = 60
        worksheet.column_dimensions["F"].width = 35
        worksheet.column_dimensions["G"].width = 15

        # Лист 2: Инструкция
        instructions_data = {
            "Шаг": [1, 2, 3, 4, 5, 6],
            "Действие": [
                "Скачайте этот шаблон",
                "Заполните файл по образцу (первая строка)",
                "Удалите первую строку с примером (или оставьте, она будет пропущена)",
                "Обязательные поля: Название, Цена",
                "Цена должна быть числом (без символов ₽, руб, $)",
                "Сохраните файл в формате .xlsx",
            ],
            "Важно": [
                "",
                "Можно заполнять несколько строк",
                "",
                "Без названия товар не будет импортирован",
                "Цена меньше или равна 0 — товар будет пропущен",
                "Максимум 100 товаров за один импорт",
            ],
        }
        df_instructions = pd.DataFrame(instructions_data)
        df_instructions.to_excel(writer, index=False, sheet_name="Инструкция")
        worksheet_inst = writer.sheets["Инструкция"]
        worksheet_inst.column_dimensions["A"].width = 8
        worksheet_inst.column_dimensions["B"].width = 40
        worksheet_inst.column_dimensions["C"].width = 50

        # Лист 3: Правила (для Ozon)
        if platform == Platform.OZON:
            ozon_rules = {
                "Поле": [
                    "Название товара",
                    "Цена",
                    "Артикул",
                    "Описание",
                    "Фото (URL)",
                    "Категория",
                ],
                "Требования": [
                    "До 150 символов. Без контактных данных, ссылок, рекламных текстов",
                    "Число. Минимум 1 рубль",
                    "Уникальный идентификатор. Латиница, цифры, дефис",
                    "До 500 символов. Подробное описание преимуществ",
                    "Прямые ссылки на фото через запятую. Максимум 10 фото",
                    "Выберите из справочника Ozon или укажите свою",
                ],
            }
            df_ozon = pd.DataFrame(ozon_rules)
            df_ozon.to_excel(writer, index=False, sheet_name="Правила Ozon")
            worksheet_ozon = writer.sheets["Правила Ozon"]
            worksheet_ozon.column_dimensions["A"].width = 20
            worksheet_ozon.column_dimensions["B"].width = 70

    output.seek(0)

    filename = f"template_{platform_name.replace(' ', '_').lower()}.xlsx"

    logger.info(f"📥 Шаблон для {platform_name} скачан")

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
