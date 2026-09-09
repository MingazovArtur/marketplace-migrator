import asyncio
import logging
from fastapi import APIRouter, HTTPException
from database.repository import repo
from models.schemas import MigrateRequest
from connectors.wildberries import WildberriesConnector
from connectors.ozon import OzonConnector
from connectors.yandex import YandexMarketConnector
from services.category_mapper import CategoryMapper
from core.platforms import Platform, PLATFORM_CONFIG

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Migration"])
category_mapper = CategoryMapper()

# Фабрика коннекторов для миграции
MIGRATION_CONNECTORS = {
    Platform.WILDBERRIES: lambda: WildberriesConnector(api_key="MOCK_WB_KEY", use_mock=True),
    Platform.OZON: lambda: OzonConnector("MOCK", "MOCK", use_mock=True),
    Platform.YANDEX: lambda: YandexMarketConnector("MOCK", "MOCK", use_mock=True),
}


async def _create_on_platform(platform: str, product_data: dict) -> dict:
    """Создает товар на целевой платформе через нужный коннектор"""
    connector_factory = MIGRATION_CONNECTORS.get(platform)
    if not connector_factory:
        return {"success": False, "error": f"Неподдерживаемая платформа: {platform}"}
    
    connector = connector_factory()
    
    # У каждого коннектора свой метод создания
    if platform == Platform.WILDBERRIES:
        return await connector.create_product(product_data)
    elif platform == Platform.OZON:
        # Для Ozon пока используем заглушку (создание товаров через API Ozon сложнее)
        logger.info(f"🎭 [MOCK] Товар '{product_data.get('name')}' создан на Ozon!")
        return {"success": True, "data": {"message": "Товар создан на Ozon (mock)"}}
    elif platform == Platform.YANDEX:
        # Для Яндекса тоже заглушка
        logger.info(f"🎭 [MOCK] Товар '{product_data.get('name')}' создан на Яндекс Маркете!")
        return {"success": True, "data": {"message": "Товар создан на Яндекс Маркете (mock)"}}
    
    return {"success": False, "error": "Не реализовано"}


@router.post("/migrate")
async def migrate_product(request: MigrateRequest):
    """Универсальная миграция товара на любую платформу"""
    product = repo.get_by_id(request.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    target = request.target_marketplace.lower()
    if target not in Platform.all_values():
        raise HTTPException(
            status_code=400, 
            detail=f"Неизвестная платформа. Доступны: {', '.join(Platform.all_values())}"
        )
    
    # === ПРОВЕРКА: нельзя переносить на ту же платформу ===
    source_platform = product.source.lower()
    
    # Определяем текущую платформу товара
    current_platform = None
    if '→' in source_platform:
        # Товар уже был перенесен, берем последнюю платформу
        last_part = source_platform.split('→')[-1].strip().lower()
        if 'ozon' in last_part:
            current_platform = 'ozon'
        elif 'wildberries' in last_part or 'wb' in last_part:
            current_platform = 'wildberries'
        elif 'яндекс' in last_part or 'yandex' in last_part:
            current_platform = 'yandex'
    else:
        # Товар еще не переносился
        if 'ozon' in source_platform:
            current_platform = 'ozon'
        elif 'wildberries' in source_platform or 'wb' in source_platform:
            current_platform = 'wildberries'
        elif 'яндекс' in source_platform or 'yandex' in source_platform:
            current_platform = 'yandex'
    
    if current_platform and current_platform == target:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя перенести товар с {current_platform} на {target}. Выберите другую платформу."
        )
    # ==========================================================
    
    repo.update(request.product_id, {"status": "processing"})
    await asyncio.sleep(1) # Имитация задержки сети

    # === ИСПРАВЛЕНИЕ 3: Обновление источника при миграции ===
    
    # 1. Определяем категорию для целевой платформы
    target_category = category_mapper.auto_map_by_text(
        product.category or "Дом и сад", 
        target
    )
    
    # 2. Формируем данные для отправки
    product_data = {
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "offer_id": f"SKU-{product.id}",
        "category": product.category or "Дом и сад",
        "target_category": target_category,
        "photos": []
    }
    
    # 3. Создаем на целевой платформе
    result = await _create_on_platform(target, product_data)
    
    # 4. Обновляем статус и источник
    if result.get("success"):
        # Правильно формируем цепочку: "Ozon (тест) → Wildberries"
        new_source = f"{product.source} → {PLATFORM_CONFIG[target]['name']}"
        
        repo.update(request.product_id, {
            "status": "success",
            "source": new_source,  # <-- ИСПОЛЬЗУЕМ new_source
            "mapped_category": target_category.get("name", "Неизвестно")
        })
        logger.info(f"✅ Миграция успешна: {product.name} → {target}")
    else:
        repo.update(request.product_id, {"status": "error"})
        logger.error(f"❌ Ошибка миграции: {result.get('error')}")
    
    return {
        "success": result.get("success", False),
        "product": repo.get_by_id(request.product_id),
        "target_platform": target,
        "target_category": target_category
    }