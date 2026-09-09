import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from database.repository import repo
from models.schemas import Product, ImportRequest
from connectors.ozon import OzonConnector
from connectors.wildberries import WildberriesConnector  # <-- ДОБАВЛЕНО
from connectors.yandex import YandexMarketConnector
from services.photo_downloader import PhotoDownloader
from services.mock_images import create_mock_image
from core.config import PHOTOS_DIR
from core.platforms import Platform, PLATFORM_CONFIG

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Import"])
photo_downloader = PhotoDownloader(base_dir=str(PHOTOS_DIR))


def _get_connector(platform: str, auth_key: str):
    """Фабрика коннекторов — выбирает нужный по платформе"""
    use_mock = False
    
    config = PLATFORM_CONFIG.get(platform)
    if config and auth_key == config["mock_key"]:
        use_mock = True
    
    if platform == Platform.OZON:
        if not use_mock and ":" not in auth_key:
            raise HTTPException(status_code=400, detail="Формат ключа Ozon: CLIENT_ID:API_KEY")
        client_id, api_key = ("MOCK", "MOCK") if use_mock else auth_key.split(":", 1)
        return OzonConnector(client_id, api_key, use_mock=use_mock), use_mock
    
    elif platform == Platform.WILDBERRIES:
        # Импорт с WB пока поддерживается в тестовом режиме
        if not use_mock:
            raise HTTPException(status_code=400, detail="Импорт с WB пока доступен только в тестовом режиме. Используйте ключ: mock_wb_key")
        return WildberriesConnector(api_key="MOCK_WB_KEY", use_mock=True), True
    
    elif platform == Platform.YANDEX:
        if not use_mock and ":" not in auth_key:
            raise HTTPException(status_code=400, detail="Формат ключа Яндекс: CLIENT_ID:TOKEN")
        client_id, token = ("MOCK", "MOCK") if use_mock else auth_key.split(":", 1)
        return YandexMarketConnector(client_id, token, use_mock=use_mock), use_mock
    
    else:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемая платформа: {platform}")


def _process_product(parsed: dict, platform: str, use_mock: bool, next_id: int) -> tuple:
    """Универсальная обработка товара: скачивание фото + создание Product"""
    if use_mock:
        product_dir = PHOTOS_DIR / f"mock_{next_id}"
        product_dir.mkdir(parents=True, exist_ok=True)
        downloaded_count = 0
        for i, _ in enumerate(parsed.get("photos", []), 1):
            img_bytes = create_mock_image(parsed["name"], i)
            with open(product_dir / f"photo_{i}.jpg", 'wb') as f:
                f.write(img_bytes)
            downloaded_count += 1
        photo_stats = {"downloaded": downloaded_count, "total": len(parsed.get("photos", []))}
    else:
        photo_stats = photo_downloader.download_photos(
            product_id=f"{platform}_{next_id}",
            photo_urls=parsed.get("photos", [])
        )
    
    source_name = PLATFORM_CONFIG.get(platform, {}).get("name", platform)
    if use_mock:
        source_name += " (тест)"
    
    new_product = Product(
        name=parsed["name"],
        source=source_name,
        price=parsed["price"],
        status="pending",
        description=parsed.get("description", "")[:200],
        photos_count=photo_stats["downloaded"],
        category=parsed.get("category", "Общая категория")
    )
    return new_product, photo_stats


@router.post("/import")
async def import_products(request: ImportRequest):
    """Универсальный импорт товаров"""
    parts = request.auth_key.split(":", 1)
    if len(parts) < 2:
        raise HTTPException(
            status_code=400, 
            detail="Формат: ПЛАТФОРМА:КЛЮЧИ. Например: ozon:test:test или yandex:test:test"
        )
    
    platform = parts[0].lower()
    actual_key = parts[1]
    
    if platform not in Platform.all_values():
        raise HTTPException(
            status_code=400, 
            detail=f"Неизвестная платформа. Доступны: {', '.join(Platform.all_values())}"
        )
    
    connector, use_mock = _get_connector(platform, actual_key)
    
    ozon_products = await connector.get_products(limit=20)
    if not ozon_products:
        raise HTTPException(status_code=404, detail="Товары не найдены")
    
    imported_count = 0
    for raw_product in ozon_products:
        if platform == Platform.OZON:
            parsed = connector.parse_ozon_product(raw_product)
        elif platform == Platform.YANDEX:
            parsed = connector.parse_yandex_product(raw_product)
        elif platform == Platform.WILDBERRIES:
            # Для WB используем заглушку парсинга, так как реальный импорт с WB сложен
            parsed = {
                "name": "Тестовый товар с Wildberries",
                "price": 990.0,
                "description": "Описание тестового товара",
                "category": "Одежда",
                "photos": ["https://example.com/wb1.jpg"]
            }
        else:
            continue
        
        new_product, photo_stats = _process_product(parsed, platform, use_mock, repo._next_id)
        repo.add(new_product)
        imported_count += 1
        
        logger.info(f"✅ [{platform.upper()}] Импортирован: {new_product.name}")
    
    return {
        "success": True,
        "platform": platform,
        "platform_name": PLATFORM_CONFIG[platform]["name"],
        "imported": imported_count,
        "total_available": len(ozon_products),
        "is_mock": use_mock
    }