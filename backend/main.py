import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import products, import_router, migrate
from services.category_mapper import CategoryMapper
from core.platforms import Platform, PLATFORM_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Marketplace Migrator API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(import_router.router)
app.include_router(migrate.router)

category_mapper = CategoryMapper()

@app.get("/api/categories/{platform}")
def get_categories(platform: str):
    """Получить категории любой платформы"""
    if platform not in Platform.all_values():
        return {"error": f"Неизвестная платформа. Доступны: {Platform.all_values()}"}
    return category_mapper.get_all_categories(platform)

@app.get("/api/platforms")
def get_platforms():
    """Получить список всех поддерживаемых платформ"""
    return {
        "platforms": [
            {"id": p.value, "name": PLATFORM_CONFIG[p.value]["name"], "color": PLATFORM_CONFIG[p.value]["color"]}
            for p in Platform
        ]
    }

@app.get("/")
def root():
    return {
        "message": "Marketplace Migrator API v2.1 — Универсальный мигратор",
        "platforms": Platform.all_values(),
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)