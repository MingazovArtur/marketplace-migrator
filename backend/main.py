import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
import re
import time
import asyncio
from connectors.ozon import OzonConnector
from connectors.wildberries import WildberriesConnector
from services.photo_downloader import PhotoDownloader
from services.mock_images import create_mock_image
from services.category_mapper import CategoryMapper

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Marketplace Migrator API")

photo_downloader = PhotoDownloader(base_dir="backend/photos")
category_mapper = CategoryMapper()

# Разрешаем запросы с фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Модели данных ===
class Product(BaseModel):
    id: int
    name: str
    source: str
    price: float
    status: str = "pending"
    description: Optional[str] = ""
    photos_count: int = 0
    mapped_category: Optional[str] = None 

class ImportRequest(BaseModel):
    url: str
    auth_key: str

class MigrateRequest(BaseModel):
    product_id: int
    target_marketplace: str

# === Хранилище в памяти (для демо) ===
products_db: List[Product] = [
    Product(id=1, name="Швабра с отжимом, 10л", source="KazanExpress", price=899, status="pending", photos_count=23),
    Product(id=2, name="Набор пластиковых мисок", source="KazanExpress", price=450, status="success", photos_count=16),
    Product(id=3, name="Ведро для швабры", source="KazanExpress", price=320, status="error", photos_count=8),
]
next_id = 4

# === Вспомогательные функции ===
def extract_product_id(url: str) -> Optional[int]:
    match = re.search(r'-(\d+)', url.split('?')[0])
    return int(match.group(1)) if match else None

def clean_html(html_text: str) -> str:
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator=" | ", strip=True)

def fetch_product_from_kazan(product_id: int, auth_key: str) -> Optional[dict]:
    """Получает данные товара через GraphQL API KazanExpress (оставлено для истории)"""
    # ... (код можно оставить, он не мешает, но сейчас мы используем Ozon)
    return None

# === API Эндпоинты ===
@app.get("/api/categories/ozon")
def get_ozon_categories():
    """Получить все категории Ozon"""
    return category_mapper.get_all_ozon_categories()

@app.get("/api/categories/wildberries")
def get_wildberries_subjects():
    """Получить все категории Wildberries"""
    return category_mapper.get_all_wildberries_subjects()

@app.get("/api/categories/mapping")
def get_mapping():
    """Получить маппинг категорий"""
    return category_mapper.data.get("mapping", {})

@app.get("/")
def root():
    return {"message": "Marketplace Migrator API работает!", "docs": "/docs"}

@app.get("/api/products")
def get_products():
    return {"total": len(products_db), "products": products_db}

@app.get("/api/stats")
def get_stats():
    total = len(products_db)
    pending = sum(1 for p in products_db if p.status == "pending")
    success = sum(1 for p in products_db if p.status == "success")
    error = sum(1 for p in products_db if p.status == "error")
    processing = sum(1 for p in products_db if p.status == "processing")
    return {"total": total, "pending": pending, "success": success, "error": error, "processing": processing}

@app.post("/api/import/ozon")
async def import_from_ozon(request: ImportRequest):
    """
    Импорт товаров с Ozon.
    Поддерживает реальные ключи и Mock-режим для тестирования без аккаунта.
    """
    global next_id

    use_mock = not (request.auth_key and ":" in request.auth_key and len(request.auth_key.split(":")[0]) > 5)
    
    if not use_mock:
        try:
            client_id, api_key = request.auth_key.split(":", 1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат ключей")
    else:
        client_id, api_key = "MOCK_ID", "MOCK_KEY"

    connector = OzonConnector(client_id, api_key, use_mock=use_mock)
    ozon_products = await connector.get_products(limit=20)
    
    if not ozon_products:
        raise HTTPException(status_code=404, detail="Товары не найдены")
    
    imported_count = 0
    for ozon_prod in ozon_products:
        parsed = connector.parse_ozon_product(ozon_prod)
        
        # === СКАЧИВАЕМ ФОТО ===
        if use_mock:
            # Для Mock-режима создаём тестовые изображения
            product_dir = Path("backend/photos") / f"mock_{next_id}"
            product_dir.mkdir(parents=True, exist_ok=True)
            
            downloaded_count = 0
            for i, _ in enumerate(parsed["photos"], 1):
                img_bytes = create_mock_image(parsed["name"], i)
                file_path = product_dir / f"photo_{i}.jpg"
                with open(file_path, 'wb') as f:
                    f.write(img_bytes)
                downloaded_count += 1
            
            photo_stats = {
                "downloaded": downloaded_count,
                "total": len(parsed["photos"]),
                "folder": str(product_dir)
            }
        else:
            # Реальное скачивание
            photo_stats = await photo_downloader.download_photos(
                product_id=f"ozon_{next_id}",
                photo_urls=parsed["photos"]
            )
        
        new_product = Product(
            id=next_id,
            name=parsed["name"],
            source="Ozon" + (" (тест)" if use_mock else ""),
            price=parsed["price"],
            status="pending",
            description=parsed["description"][:200] if parsed["description"] else "",
            photos_count=photo_stats["downloaded"]
        )
        products_db.append(new_product)
        next_id += 1
        imported_count += 1
        
        logger.info(f"✅ Товар '{new_product.name}' импортирован. Фото: {photo_stats['downloaded']}/{photo_stats['total']}")
    
    return {
        "success": True, 
        "imported": imported_count,
        "total_available": len(ozon_products),
        "is_mock": use_mock
    }

@app.post("/api/migrate")
async def migrate_product(request: MigrateRequest):
    product = next((p for p in products_db if p.id == request.product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    product.status = "processing"
    await asyncio.sleep(1) # Имитация задержки сети
    
    if request.target_marketplace.lower() == "wildberries":
        wb_connector = WildberriesConnector(api_key="MOCK_WB_API_KEY", use_mock=True)
        
        mock_product_data = {
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "offer_id": f"SKU-{product.id}",
            "category": product.source.split(" → ")[0] if " → " in product.source else "Дом и сад", # Берем примерную категорию
            "photos": []
        }
        
        result = await wb_connector.create_product(mock_product_data)
        
        if result.get("success"):
            product.status = "success"
            product.source = f"{product.source} → Wildberries"
            # Сохраняем информацию о маппинге для отображения (в реальном приложении это шло бы в БД)
            product.mapped_category = result["data"].get("mapped_category", {}).get("name", "Неизвестно")
        else:
            product.status = "error"
    else:
        product.status = "success"
        product.source = f"{product.source} → {request.target_marketplace}"
    
    return {"success": True, "product": product}

@app.delete("/api/products/{product_id}")
def delete_product(product_id: int):
    global products_db
    products_db = [p for p in products_db if p.id != product_id]
    return {"success": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)