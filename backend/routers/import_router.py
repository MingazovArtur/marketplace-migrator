import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from database.repository import repo
from models.schemas import Product, ImportRequest
from connectors.ozon import OzonConnector
from connectors.wildberries import WildberriesConnector
from connectors.yandex import YandexMarketConnector
from services.photo_downloader import PhotoDownloader
from services.mock_images import create_mock_image
from core.config import PHOTOS_DIR
from core.platforms import Platform, PLATFORM_CONFIG
from fastapi import UploadFile, File
from services.file_parser import parse_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Import"])
photo_downloader = PhotoDownloader(base_dir=str(PHOTOS_DIR))


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
    elif platform == Platform.YANDEX:
        source_name += " (YML)"
    
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
    """
    Универсальный импорт товаров.
    
    Форматы auth_key:
    - Ozon: "ozon:test:test" или "ozon:CLIENT_ID:API_KEY"
    - Яндекс: "yandex:URL_ФИДА" или "yandex:test:test" (Mock)
    - WB: "wildberries:mock_wb_key" (только Mock)
    """
    parts = request.auth_key.split(":", 1)
    if len(parts) < 2:
        raise HTTPException(
            status_code=400, 
            detail="Формат: ПЛАТФОРМА:ДАННЫЕ. Например: yandex:https://shop.ru/yml.xml"
        )
    
    platform = parts[0].lower()
    data = parts[1]
    
    if platform not in Platform.all_values():
        raise HTTPException(
            status_code=400, 
            detail=f"Неизвестная платформа. Доступны: {', '.join(Platform.all_values())}"
        )
    
    # === OZON ===
    if platform == Platform.OZON:
        use_mock = data == "test:test"
        if not use_mock and ":" not in data:
            raise HTTPException(status_code=400, detail="Формат ключа Ozon: CLIENT_ID:API_KEY")
        
        client_id, api_key = ("MOCK", "MOCK") if use_mock else data.split(":", 1)
        connector = OzonConnector(client_id, api_key, use_mock=use_mock)
        products_raw = await connector.get_products(limit=20)
        
        if not products_raw:
            raise HTTPException(status_code=404, detail="Товары не найдены")
        
        imported_count = 0
        for raw in products_raw:
            parsed = connector.parse_ozon_product(raw)
            new_product, _ = _process_product(parsed, platform, use_mock, repo._next_id)
            repo.add(new_product)
            imported_count += 1
        
        return {
            "success": True,
            "platform": platform,
            "platform_name": PLATFORM_CONFIG[platform]["name"],
            "imported": imported_count,
            "total_available": len(products_raw),
            "is_mock": use_mock
        }
    
    # === YANDEX (YML-фиды) ===
        # === YANDEX (Seller API или YML или Mock) ===
    elif platform == Platform.YANDEX:
        use_mock = data == "test:test"
        
        if use_mock:
            from connectors.yandex import YandexMarketConnector # Импортируем старый mock-коннектор
            connector = YandexMarketConnector(use_mock=True)
            products_raw = await connector.get_products(limit=50)
        elif ":" in data:
            # Формат: campaign_id:oauth_token
            campaign_id, oauth_token = data.split(":", 1)
            from connectors.yandex_seller import YandexSellerConnector
            connector = YandexSellerConnector(campaign_id=campaign_id, oauth_token=oauth_token)
            
            try:
                offers_raw = await connector.get_products(limit=100)
                products_raw = [connector.parse_yandex_offer(offer) for offer in offers_raw]
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        else:
            # Пытаемся обработать как URL YML-фида (старый способ)
            from connectors.yandex import YandexMarketConnector
            connector = YandexMarketConnector(source=data, use_mock=False, api_type="yml")
            try:
                products_raw = await connector.get_products(limit=50)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        if not products_raw:
            raise HTTPException(status_code=404, detail="Товары не найдены")
        
        imported_count = 0
        for raw in products_raw:
            # Для Seller API raw уже распарсен, для YML нужен parse_yandex_product
            parsed = raw if "source" in raw and raw["source"] == "yandex_seller_api" else connector.parse_yandex_product(raw)
            
            new_product, _ = _process_product(parsed, platform, use_mock, repo._next_id)
            repo.add(new_product)
            imported_count += 1
        
        return {
            "success": True,
            "platform": platform,
            "platform_name": PLATFORM_CONFIG[platform]["name"],
            "imported": imported_count,
            "total_available": len(products_raw),
            "is_mock": use_mock
        }
    
    # === WILDBERRIES (только Mock) ===
    elif platform == Platform.WILDBERRIES:
        if data != "mock_wb_key":
            raise HTTPException(
                status_code=400, 
                detail="Импорт с WB пока доступен только в тестовом режиме. Используйте ключ: mock_wb_key"
            )
        
        connector = WildberriesConnector(api_key="MOCK_WB_KEY", use_mock=True)
        # WB не имеет метода get_products, используем заглушку
        products_raw = [{
            "name": "Тестовый товар с Wildberries",
            "price": 990.0,
            "description": "Описание тестового товара WB",
            "category": "Одежда",
            "photos": ["https://example.com/wb1.jpg"]
        }]
        
        imported_count = 0
        for raw in products_raw:
            new_product, _ = _process_product(raw, platform, True, repo._next_id)
            repo.add(new_product)
            imported_count += 1
        
        return {
            "success": True,
            "platform": platform,
            "platform_name": PLATFORM_CONFIG[platform]["name"],
            "imported": imported_count,
            "total_available": len(products_raw),
            "is_mock": True
        }
    
    else:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемая платформа: {platform}")

@router.post("/import/file")
async def import_from_file(
    platform: str,
    file: UploadFile = File(...)
):
    """
    Универсальный импорт товаров из Excel (.xlsx) или CSV (.csv) файла
    """
    platform = platform.lower()
    if platform not in Platform.all_values():
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform}")
    
    # Проверяем тип файла
    file_ext = file.filename.split('.')[-1].lower()
    if file_ext not in ['xlsx', 'csv']:
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .xlsx и .csv")
    
    try:
        # Читаем содержимое файла
        file_content = await file.read()
        
        # Парсим файл
        parsed_products = parse_file(file_content, platform, file_ext)
        
        if not parsed_products:
            raise HTTPException(status_code=400, detail="Не найдено ни одного корректного товара в файле")
        
        # Сохраняем в репозиторий
        imported_count = 0
        for parsed in parsed_products:
            new_product = Product(
                name=parsed["name"],
                source=f"{PLATFORM_CONFIG[platform]['name']} (из файла)",
                price=parsed["price"],
                status="pending",
                description=parsed["description"],
                photos_count=len(parsed["photos"]),
                category=parsed["category"]
            )
            repo.add(new_product)
            imported_count += 1
            
            # Если есть фото, запускаем скачивание (асинхронно, но для простоты синхронно в цикле)
            if parsed["photos"]:
                photo_stats = await photo_downloader.download_photos(
                    product_id=f"file_{repo._next_id - 1}",
                    photo_urls=parsed["photos"]
                )
                # Обновляем количество скачанных фото
                repo.update(repo._next_id - 1, {"photos_count": photo_stats["downloaded"]})
        
        return {
            "success": True,
            "platform": platform,
            "platform_name": PLATFORM_CONFIG[platform]["name"],
            "imported": imported_count,
            "total_in_file": len(parsed_products),
            "message": f"Успешно импортировано {imported_count} товаров из файла"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка импорта файла: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при обработке файла")