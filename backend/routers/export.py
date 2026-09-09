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
    products = repo.get_all()
    
    if not products:
        # Если товаров нет, создаем пустой отчет с заголовками
        data = []
    else:
        data = []
        for p in products:
            # Превращаем Pydantic модель в словарь
            p_dict = p.model_dump()
            
            # Эвристика для "Новой цены" (например, наценка 15% при переносе на WB)
            # В реальном приложении это может браться из истории миграций
            new_price = p_dict["price"]
            if "wildberries" in p_dict["source"].lower() or "→ Wildberries" in p_dict["source"]:
                new_price = round(p_dict["price"] * 1.15, 2)
            
            data.append({
                "ID": p_dict["id"],
                "Название товара": p_dict["name"],
                "Артикул (SKU)": f"SKU-{p_dict['id']}",
                "Источник": p_dict["source"],
                "Старая цена (₽)": p_dict["price"],
                "Новая цена (₽)": new_price,
                "Категория (источник)": p_dict.get("category") or "Не указана",
                "Категория (назначение)": p_dict.get("mapped_category") or "Не маппировалось",
                "Статус": p_dict["status"],
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