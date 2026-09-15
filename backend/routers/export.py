"""
Роутер для экспорта данных в Excel
"""
import io
import logging
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import pandas as pd
from database.repository import repo
from core.auth import get_current_user
from database.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Export"])


@router.get("/export/report")
def export_migration_report(current_user: User = Depends(get_current_user)):
    """
    Генерирует и скачивает Excel-файл с отчетом по товарам текущего пользователя.
    Администратор получает отчет по всем товарам.
    """
    is_admin = current_user.role == "admin"
    products = repo.get_all(user_id=current_user.id, is_admin=is_admin)
    
    if not products:
        data = []
    else:
        data = []
        for p in products:
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
    
    # Если данных нет, создаем DataFrame с нужными колонками
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
        worksheet = writer.sheets['Отчет миграции']
        worksheet.column_dimensions['B'].width = 40
        worksheet.column_dimensions['D'].width = 20
    
    output.seek(0)
    filename = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    
    logger.info(f" Сформирован отчет Excel: {len(data)} строк для пользователя {current_user.username}")
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )