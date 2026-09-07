from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
import re
import time

app = FastAPI(title="Marketplace Migrator API")

# Разрешаем запросы с фронтенда (Vite работает на порту 5173)
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
    """Получает данные товара через GraphQL API KazanExpress"""
    graphql_url = "https://graphql.kazanexpress.ru/"
    query = """
    query GetProduct($id: Int!) {
      product(id: $id) {
        id
        title
        shortDescription
        description
        minSellPrice
        rating
        category { title }
        photos { original { high } }
        skuList { id, skuTitle, sellPrice, availableAmount }
      }
    }
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": auth_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    payload = {"query": query, "variables": {"id": product_id}}
    
    try:
        response = requests.post(graphql_url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("product")
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return None

# === API Эндпоинты ===

@app.get("/")
def root():
    return {"message": "Marketplace Migrator API работает!", "docs": "/docs"}

@app.get("/api/products")
def get_products():
    """Получить список всех товаров"""
    return {"total": len(products_db), "products": products_db}

@app.get("/api/stats")
def get_stats():
    """Получить статистику"""
    total = len(products_db)
    pending = sum(1 for p in products_db if p.status == "pending")
    success = sum(1 for p in products_db if p.status == "success")
    error = sum(1 for p in products_db if p.status == "error")
    processing = sum(1 for p in products_db if p.status == "processing")
    return {
        "total": total,
        "pending": pending,
        "success": success,
        "error": error,
        "processing": processing
    }

@app.post("/api/import")
def import_product(request: ImportRequest):
    """Импортировать товар по ссылке"""
    global next_id
    
    product_id = extract_product_id(request.url)
    if not product_id:
        raise HTTPException(status_code=400, detail="Не удалось извлечь ID товара из ссылки")
    
    # Получаем данные с KazanExpress
    product_data = fetch_product_from_kazan(product_id, request.auth_key)
    if not product_data:
        raise HTTPException(status_code=404, detail="Товар не найден или ошибка API")
    
    # Определяем цену
    sku_list = product_data.get("skuList", [])
    price = sku_list[0].get("sellPrice", product_data.get("minSellPrice", 0)) / 100 if sku_list else 0
    
    # Считаем фото
    photos_count = len(product_data.get("photos", []))
    
    # Создаём новый товар
    new_product = Product(
        id=next_id,
        name=product_data.get("title", "Без названия"),
        source="KazanExpress",
        price=round(price, 2),
        status="pending",
        description=clean_html(product_data.get("description", ""))[:200],
        photos_count=photos_count
    )
    products_db.append(new_product)
    next_id += 1
    
    return {"success": True, "product": new_product}

@app.post("/api/migrate")
def migrate_product(request: MigrateRequest):
    """Запустить миграцию товара"""
    # Ищем товар
    product = next((p for p in products_db if p.id == request.product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    # Меняем статус на "processing"
    product.status = "processing"
    
    # Имитация задержки миграции (в реальности здесь будет вызов API целевого маркетплейса)
    time.sleep(2)
    
    # Имитация успеха/ошибки (для демо)
    product.status = "success"
    product.source = f"{product.source} → {request.target_marketplace}"
    
    return {"success": True, "product": product}

@app.delete("/api/products/{product_id}")
def delete_product(product_id: int):
    """Удалить товар"""
    global products_db
    products_db = [p for p in products_db if p.id != product_id]
    return {"success": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)