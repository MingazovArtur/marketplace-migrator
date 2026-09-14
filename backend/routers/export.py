"""
Роутер для экспорта данных в Excel
"""
import io
import logging
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import pandas as pd
from database.repository import repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Export"])


@router.get("/export/report")
def export_migration_report():
    """
    Генерирует и скачивает Excel-файл с отчетом по всем товарам
    """
    # repo.get_all() теперь возвращает список словарей, а не Pydantic-моделей
    products = repo.get_all()
    
    if not products:
        data = []
    else:
        data = []
        for p in products:
            # p - это уже словарь, поэтому используем p["ключ"], а не p.model_dump()
            
            # Эвристика для "Новой цены" (наценка 15% при переносе на WB)
            new_price = p["price"]
            if "wildberries" in p["source"].lower() or "→ Wildberries" in p["source"]:
                new_price = round(p["price"] * 1.15, 2)
            
            data.append({
                "ID": p["id"],
                "Название товара": p["name"],
                "Артикул (SKU)": f"SKU-{p['id']}",
                "Источник": p["source"],
                "Старая цена (₽)": p["price"],
                "Новая цена (₽)": new_price,
                "Категория (источник)": p.get("category") or "Не указана",
                "Категория (назначение)": p.get("mapped_category") or "Не маппировалось",
                "Статус": p["status"],
                "Дата выгрузки": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
    
    # Создаем DataFrame
    df = pd.DataFrame(data)
    
    # Если данных нет, создаем DataFrame с нужными колонками, чтобы файл не был пустым
    if df.empty:
        df = pd.DataFrame(columns=[
            "ID", "Название товара", "Артикул (SKU)", "Источник", 
            "Старая цена (₽)", "Новая цена (₽)", "Категория (источник)", 
            "Категория (назначение)", "Статус", "Дата выгрузки"
        ])
    
    # Записываем в буфер в памяти
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Отчет миграции')
        
        # Немного украсим таблицу (ширина колонок)
        worksheet = writer.sheets['Отчет миграции']
        worksheet.column_dimensions['B'].width = 40 # Название
        worksheet.column_dimensions['D'].width = 20 # Источник
    
    output.seek(0)
    
    filename = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    
    logger.info(f"📊 Сформирован отчет Excel: {len(data)} строк")
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )