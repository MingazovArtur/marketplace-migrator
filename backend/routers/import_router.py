"""
Роутер импорта товаров (API-ключ, YML, Excel/CSV).

Режимы импорта файла:
  - create  — только новые карточки
  - upsert  — обновление совпадений по external_id / sku

Все операции логируются в file_operation_logs (журнал)
и import_export_stats (статистика с замером времени).

Rate-limits (на идентификатор: user_id или IP):
  - /import/preview : 30/min
  - /import (key/yml): 10/min, 100/day
  - /import/file    : 10/min, 100/day
"""
import logging
import time

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
)
from pydantic import BaseModel

from core.auth import get_current_user
from core.platforms import PLATFORM_CONFIG
from core.rate_limit import limiter
from database.models import User
from database.repository import repo, op_log, stats_repo, variant_repo
from models.schemas import ProductCreate
from parsers.file_parser import parse_file, preview_file
from parsers.yml_parser import YmlParser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Import"])


class ImportRequest(BaseModel):
    key: str = ""
    full_key: str = ""

    def get_key(self) -> str:
        """Единая точка получения ключа (поддерживает оба поля фронта)."""
        return (self.key or self.full_key).strip()


def _source_label(platform: str) -> str:
    """Каноническая метка источника импорта из файла."""
    cfg = PLATFORM_CONFIG.get(platform) or {}
    return f"{cfg.get('name', platform)} (Файл)"


# ==================== ПРЕДПРОСМОТР ФАЙЛА ====================
@limiter.limit("30/minute")
@router.post("/import/preview")
async def preview_import(
    request: Request,                                       # ← добавлен для slowapi
    platform: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Предпросмотр файла: первые строки + ошибки парсинга (без записи в БД)."""
    if platform not in PLATFORM_CONFIG:
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform}")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")

    file_type = "csv" if file.filename.lower().endswith(".csv") else "xlsx"
    if file_type not in ("csv", "xlsx"):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .csv и .xlsx")

    try:
        contents = await file.read()
        preview_data = preview_file(contents, platform, file_type, max_rows=10)
        return {"success": True, "preview": preview_data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка предпросмотра: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# ==================== ИМПОРТ ПО КЛЮЧУ / YML / МОК ====================
@limiter.limit("10/minute;100/day")
@router.post("/import")
async def import_products(
    request: Request,                                       # ← добавлен для slowapi
    payload: ImportRequest,                                 # ← переименован (был request)
    current_user: User = Depends(get_current_user),
):
    """Импорт по API-ключу, мок-ключу или YML-ссылке."""
    t0 = time.perf_counter()
    auth_key = payload.get_key()                            # ← использование нового имени

    if not auth_key:
        raise HTTPException(status_code=400, detail="Не указан API-ключ или YML-ссылка")

    is_mock = (
        auth_key.lower() in ("test:test", "mock_wb_key", "mock_ozon_key", "mock_yandex_key")
        or auth_key.lower().endswith(":test:test")
    )

    # ---------- Мок-импорт (для демо и тестов) ----------
    if is_mock:
        if "yandex" in auth_key.lower():
            platform = "yandex"
        elif "wb" in auth_key.lower() or "wildberries" in auth_key.lower():
            platform = "wildberries"
        else:
            platform = "ozon"

        mock_products = [
            ProductCreate(
                name="Швабра с отжимом и ведром, самоочищающаяся, 2 насадки, 10 л",
                source=f"{PLATFORM_CONFIG[platform]['name']} (тест)",
                price=899.0, status="pending",
                description="<p>Удобная швабра с ведром для быстрой уборки.</p>",
                photos_count=3, category="Дом и сад > Уборка > Швабры",
                user_id=current_user.id,
            ),
            ProductCreate(
                name="Смартфон Xiaomi Redmi Note 12 4/128GB",
                source=f"{PLATFORM_CONFIG[platform]['name']} (тест)",
                price=12990.0, status="pending",
                description="Отличный смартфон с хорошей камерой.",
                photos_count=5, category="Электроника > Смартфоны",
                user_id=current_user.id,
            ),
            ProductCreate(
                name="Чай черный байкальский, 100 пакетиков",
                source=f"{PLATFORM_CONFIG[platform]['name']} (тест)",
                price=250.0, status="pending",
                description="Натуральный черный чай.",
                photos_count=1, category="Продукты питания > Чай и кофе > Чай",
                user_id=current_user.id,
            ),
        ]

        imported_count = 0
        for p in mock_products:
            repo.add(p)
            imported_count += 1

        duration_ms = int((time.perf_counter() - t0) * 1000)
        op_log.log_file_operation(
            user_id=current_user.id,
            operation="import_api",
            platform=platform,
            filename=None,
            mode=None,
            status="success",
            total_rows=imported_count,
            imported=imported_count,
            updated=0,
            failed=0,
            errors=[],
        )
        stats_repo.record(
            user_id=current_user.id,
            operation="import_api",
            platform=platform,
            status="success",
            total_items=imported_count,
            success_items=imported_count,
            failed_items=0,
            duration_ms=duration_ms,
        )

        return {
            "success": True,
            "imported": imported_count,
            "updated": 0,
            "platform_name": PLATFORM_CONFIG[platform]["name"],
            "is_mock": True,
        }

    # ---------- YML-фид (Яндекс Маркет) ----------
    if auth_key.startswith(("http://", "https://")):
        try:
            yml_products = YmlParser().fetch_and_parse(auth_key)
        except Exception as e:
            logger.error(f"Ошибка парсинга YML: {e}")
            duration_ms = int((time.perf_counter() - t0) * 1000)
            op_log.log_file_operation(
                user_id=current_user.id,
                operation="import_yml",
                platform="yandex",
                filename=auth_key[:100],
                mode=None,
                status="error",
                total_rows=0, imported=0, updated=0, failed=0,
                errors=[{"error": f"Ошибка парсинга YML: {str(e)}"}],
            )
            stats_repo.record(
                user_id=current_user.id,
                operation="import_yml",
                platform="yandex",
                status="error",
                total_items=0, success_items=0, failed_items=0,
                duration_ms=duration_ms,
            )
            raise HTTPException(status_code=400, detail=f"Ошибка парсинга YML: {e}")

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
                photos_count=len(p_data.get("photos", [])),
                category=p_data.get("category", "Не указана"),
                user_id=current_user.id,
            )
            repo.add(product_obj)
            imported_count += 1

        duration_ms = int((time.perf_counter() - t0) * 1000)
        op_log.log_file_operation(
            user_id=current_user.id,
            operation="import_yml",
            platform="yandex",
            filename=auth_key[:100],
            mode=None,
            status="success",
            total_rows=imported_count,
            imported=imported_count,
            updated=0,
            failed=0,
            errors=[],
        )
        stats_repo.record(
            user_id=current_user.id,
            operation="import_yml",
            platform="yandex",
            status="success",
            total_items=imported_count,
            success_items=imported_count,
            failed_items=0,
            duration_ms=duration_ms,
        )

        return {
            "success": True,
            "imported": imported_count,
            "updated": 0,
            "platform_name": "Яндекс Маркет",
            "is_mock": False,
        }

    # ---------- Реальные API площадок: пока не реализовано ----------
    return {
        "success": False,
        "imported": 0,
        "updated": 0,
        "platform_name": "Неизвестно",
        "is_mock": False,
        "detail": "Реальный API импорт пока в разработке. Используйте 'test:test' или YML-ссылку.",
    }


# ==================== ИМПОРТ ИЗ ФАЙЛА (XLSX / CSV) ====================
@limiter.limit("10/minute;100/day")
@router.post("/import/file")
async def import_from_file(
    request: Request,                                       # ← добавлен для slowapi
    platform: str = Form(...),
    mode: str = Form("create"),   # create | upsert
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Импорт товаров из Excel (.xlsx) или CSV.
    mode=upsert — обновляет существующие карточки по external_id/sku вместо дублей.
    Варианты (SKU) из файла сохраняются в product_variants.
    """
    t0 = time.perf_counter()

    if platform not in PLATFORM_CONFIG:
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform}")
    if mode not in ("create", "upsert"):
        raise HTTPException(status_code=400, detail="Режим должен быть create или upsert")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")

    file_type = "csv" if file.filename.lower().endswith(".csv") else "xlsx"
    if file_type not in ("csv", "xlsx"):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .csv и .xlsx")

    # ---------- Парсинг ----------
    try:
        contents = await file.read()
        result = parse_file(contents, platform, file_type)
    except ValueError as e:
        stats_repo.record(
            user_id=current_user.id, operation="import_file", platform=platform,
            status="error", duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка парсинга файла: {e}")
        stats_repo.record(
            user_id=current_user.id, operation="import_file", platform=platform,
            status="error", duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при обработке файла")

    products_data = result["products"]
    errors = result["errors"]

    if not products_data:
        op_log.log_file_operation(
            user_id=current_user.id,
            operation="import_file",
            platform=platform,
            filename=file.filename,
            mode=mode,
            status="error",
            total_rows=result["total_rows"],
            imported=0, updated=0, failed=len(errors),
            errors=errors[:10],
        )
        stats_repo.record(
            user_id=current_user.id, operation="import_file", platform=platform,
            status="error", total_items=result["total_rows"],
            success_items=0, failed_items=len(errors),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise HTTPException(status_code=400, detail="Не найдено валидных товаров в файле. Проверьте ошибки.")

    # ---------- Запись в БД ----------
    source_label = _source_label(platform)
    imported = 0
    updated = 0

    for p_data in products_data:
        payload_dict = dict(
            name=p_data.get("name"),
            source=source_label,
            price=p_data.get("price", 0),
            status="pending",
            description=p_data.get("description", ""),
            photos_count=len(p_data.get("photos", [])),
            category=p_data.get("category", "Не указана"),
            sku=p_data.get("sku"),
            external_id=p_data.get("external_id"),
            brand=p_data.get("brand"),
            photos=p_data.get("photos", []),
            sku_count=p_data.get("sku_count", 1),
        )
        variants = p_data.get("variants") or []

        existing = None
        if mode == "upsert":
            existing = repo.find_by_external(
                user_id=current_user.id,
                source=source_label,
                external_id=p_data.get("external_id"),
                sku=p_data.get("sku"),
            )

        if existing:
            repo.update(existing["id"], payload_dict, user_id=current_user.id)
            if variants:
                variant_repo.set_variants(existing["id"], variants)
            updated += 1
        else:
            product_obj = ProductCreate(user_id=current_user.id, **payload_dict)
            created = repo.add(product_obj)
            if created and variants:
                variant_repo.set_variants(created["id"], variants)
            imported += 1

    logger.info(
        f"✅ Импорт завершён: создано {imported}, обновлено {updated}, ошибок {len(errors)}",
        extra={"user_id": current_user.id, "platform": platform},
    )

    # ---------- Логирование ----------
    warnings = result.get("warnings", [])
    message = f"Импорт завершён: создано {imported}, обновлено {updated}"
    if warnings:
        message += ". " + " ".join(w["message"] for w in warnings)

    status_val = "success" if not errors else "partial"

    op_log.log_file_operation(
        user_id=current_user.id,
        operation="import_file",
        platform=platform,
        filename=file.filename,
        mode=mode,
        status=status_val,
        total_rows=result["total_rows"],
        imported=imported,
        updated=updated,
        failed=len(errors),
        errors=errors[:10],
    )
    stats_repo.record(
        user_id=current_user.id,
        operation="import_file",
        platform=platform,
        status=status_val,
        total_items=result["total_rows"],
        success_items=imported + updated,
        failed_items=len(errors),
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )

    return {
        "success": True,
        "message": message,
        "imported": imported,
        "updated": updated,
        "total_rows": result["total_rows"],
        "failed": len(errors),
        "errors": errors[:20],
        "warnings": warnings,
    }