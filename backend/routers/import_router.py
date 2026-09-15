"""
Роутер для импорта товаров (API ключи, YML, Excel/CSV)
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from database.repository import repo
from database.models import User
from models.schemas import ImportRequest, ProductCreate
from core.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Import"])


@router.post("/import")
async def import_products(
    request: ImportRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Импорт товаров по API ключу, Mock-ключу или YML-ссылке
    """
    # 🔍 ПУЛЕНЕПРОБИВАЕМОЕ ИЗВЛЕЧЕНИЕ: защищаемся от случайных массивов/кортежей с фронтенда
    raw_key = request.auth_key
    
    if isinstance(raw_key, (list, tuple)):
        auth_key = str(raw_key[0]).strip() if raw_key else ""
    else:
        auth_key = str(raw_key or "").strip()
    
    print(f"🔍 [IMPORT DEBUG] raw_key тип: {type(raw_key)}, значение: {raw_key}")
    print(f"🔍 [IMPORT DEBUG] Итоговый очищенный auth_key: '{auth_key}'")
    
    # 1. MOCK-РЕЖИМ (для тестирования)
    # Проверяем, является ли ключ известным mock-ключом ИЛИ заканчивается на :test:test
    is_mock = (
        auth_key.lower() in ["test:test", "mock_wb_key", "mock_ozon_key", "mock_yandex_key"] or 
        auth_key.lower().endswith(":test:test")
    )
    
    if is_mock:
        # Умно определяем платформу из самого ключа
        if "yandex" in auth_key.lower():
            platform = "yandex"
        elif "wb" in auth_key.lower() or "wildberries" in auth_key.lower():
            platform = "wildberries"
        else:
            platform = "ozon"
            
        print(f"✅ [IMPORT DEBUG] Активирован MOCK-режим для платформы: {platform}")
        
        # Создаем тестовые товары. ВАЖНО: указываем user_id текущего пользователя!
        mock_products = [
            ProductCreate(
                name="Швабра с отжимом и ведром, самоочищающаяся, 2 насадки, 10 л",
                source=f"{platform.capitalize()} (тест)",
                price=899.0,
                status="pending",
                description="<p>Удобная швабра с ведром для быстрой уборки.</p>",
                photos_count=3,
                category="Дом и сад > Уборка > Швабры",
                user_id=current_user.id
            ),
            ProductCreate(
                name="Смартфон Xiaomi Redmi Note 12 4/128GB",
                source=f"{platform.capitalize()} (тест)",
                price=12990.0,
                status="pending",
                description="Отличный смартфон с хорошей камерой.",
                photos_count=5,
                category="Электроника > Смартфоны",
                user_id=current_user.id
            ),
            ProductCreate(
                name="Чай черный байкальский, 100 пакетиков",
                source=f"{platform.capitalize()} (тест)",
                price=250.0,
                status="pending",
                description="Натуральный черный чай.",
                photos_count=1,
                category="Продукты питания > Чай и кофе > Чай",
                user_id=current_user.id
            )
        ]
        
        imported_count = 0
        for p in mock_products:
            repo.add(p)
            imported_count += 1
        
        platform_name_map = {
            "ozon": "Ozon",
            "wildberries": "Wildberries",
            "yandex": "Яндекс Маркет"
        }
        
        return {
            "success": True,
            "imported": imported_count,
            "platform_name": platform_name_map.get(platform, platform.capitalize()),
            "is_mock": True
        }

    # 2. ИМПОРТ ЧЕРЕЗ YML-ФИД (Яндекс Маркет)
    if auth_key.startswith("http://") or auth_key.startswith("https://"):
        try:
            from services.yml_parser import parse_yml_url
            
            # Парсим YML (функция должна возвращать список словарей)
            yml_products = parse_yml_url(auth_key)
            
            if not yml_products:
                raise HTTPException(status_code=400, detail="Не найдено товаров в YML-фиде")
            
            imported_count = 0
            for p_data in yml_products:
                product_obj = ProductCreate(
                    name=p_data.get("name", "Без названия"),
                    source="Яндекс Маркет (YML)",
                    price=float(p_data.get("price", 0)),
                    status="pending",
                    description=p_data.get("description", ""),
                    photos_count=len(p_data.get("pictures", [])) if p_data.get("pictures") else 0,
                    category=p_data.get("category", "Не указана"),
                    user_id=current_user.id  # ВАЖНО: привязка к пользователю
                )
                repo.add(product_obj)
                imported_count += 1
                
            return {
                "success": True,
                "imported": imported_count,
                "platform_name": "Яндекс Маркет",
                "is_mock": False
            }
        except Exception as e:
            logger.error(f"Ошибка парсинга YML: {e}")
            raise HTTPException(status_code=400, detail=f"Ошибка парсинга YML: {str(e)}")

    # 3. РЕАЛЬНЫЙ API (Ozon / Yandex Seller) - заглушка для будущего расширения
    return {
        "success": False,
        "imported": 0,
        "platform_name": "Неизвестно",
        "is_mock": False,
        "detail": "Реальный API импорт пока в разработке. Для теста используйте 'test:test' или YML-ссылку."
    }


@router.post("/import/file")
async def import_from_file(
    platform: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Импорт товаров из Excel (.xlsx) или CSV файла
    """
    if not file.filename.lower().endswith(('.csv', '.xlsx')):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .csv и .xlsx")
    
    try:
        # Читаем содержимое файла
        contents = await file.read()
        
        # Импортируем и используем парсер файлов
        from services.file_parser import parse_file
        parsed_data = parse_file(contents, file.filename)
        
        if not parsed_data:
            raise HTTPException(status_code=400, detail="Не удалось распознать данные в файле или файл пуст")
        
        imported_count = 0
        for row in parsed_data:
            # Безопасное преобразование цены
            raw_price = row.get("price") or row.get("Цена", 0)
            try:
                clean_price = float(str(raw_price).replace(",", ".").replace(" ", ""))
            except ValueError:
                clean_price = 0.0
                
            # Безопасное преобразование количества фото
            raw_photos = row.get("photos_count") or row.get("Фото", 0)
            try:
                clean_photos = int(raw_photos)
            except ValueError:
                clean_photos = 0

            product_obj = ProductCreate(
                name=row.get("name") or row.get("Название", "Без названия"),
                source=f"{platform.capitalize()} (Файл)",
                price=clean_price,
                status="pending",
                description=row.get("description") or row.get("Описание", ""),
                photos_count=clean_photos,
                category=row.get("category") or row.get("Категория", "Не указана"),
                user_id=current_user.id  # ВАЖНО: привязка к пользователю
            )
            repo.add(product_obj)
            imported_count += 1
            
        return {
            "success": True,
            "message": f"Успешно импортировано {imported_count} товаров из файла",
            "imported": imported_count
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Ошибка в данных файла: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка импорта файла: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при обработке файла")