import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import products, import_router, migrate, export, auth
from services.category_mapper import CategoryMapper
from core.platforms import Platform, PLATFORM_CONFIG

from routers import categories

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Marketplace Migrator API")

# === CORS настройка (обязательно до роутеров) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Подключение роутеров ===
app.include_router(products.router)
app.include_router(import_router.router)
app.include_router(migrate.router)
app.include_router(export.router)
app.include_router(auth.router)
app.include_router(categories.router)

category_mapper = CategoryMapper()

@app.get("/api/categories/{platform}")
def get_categories(platform: str):
    if platform not in Platform.all_values():
        return {"error": f"Неизвестная платформа. Доступны: {Platform.all_values()}"}
    return category_mapper.get_all_categories(platform)

@app.get("/api/platforms")
def get_platforms():
    return {
        "platforms": [
            {"id": p.value, "name": PLATFORM_CONFIG[p.value]["name"], "color": PLATFORM_CONFIG[p.value]["color"]}
            for p in Platform
        ]
    }

@app.get("/")
def root():
    return {
        "message": "Marketplace Migrator API v3.2 (Multi-user Ready)",
        "platforms": Platform.all_values(),
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)