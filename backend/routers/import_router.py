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

B-1 (неделя 2): CPU-тяжёлый парсинг (openpyxl) и цикл записи в БД
выносятся из async-роута в threadpool (asyncio.to_thread) —
больше не блокируют event loop на весь импорт.
"""

import asyncio
import logging
import os
import time

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel

from connectors.yandex_seller import YandexSellerConnector
from core.auth import get_current_user
from core.platforms import PLATFORM_CONFIG
from core.rate_limit import limiter
from database.models import User
from database.repository import op_log, repo, stats_repo
from parsers import parse_file, preview_file
from parsers.yml_parser import YmlParser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Import"])

MAX_IMPORT_FILE_SIZE = 15 * 1024 * 1024  # 15 МБ


def _persist_imported_products(
    user_id: int, source_label: str, mode: str, products_data: list
) -> tuple[int, int]:
    """
    Синхронная запись распарсенных товаров в БД (create/upsert + варианты + атрибуты).
    Вызывается через asyncio.to_thread из async-роута — синхронные repo-вызовы
    не блокируют event loop (B-1). Возвращает (imported, updated).

    P-2 (неделя 3): запись переведена на repo.bulk_import — одна сессия на весь
    импорт, один commit на чанк (200 товаров), совпадения для upsert выбираются
    одним запросом на чанк. Было: 4 сессии и 2-4 commit'а на каждый товар,
    импорт 500 карточек = ~2000 сессий и ~1500 commit'ов.
    """
    return repo.bulk_import(
        user_id=user_id,
        source_label=source_label,
        mode=mode,
        products_data=products_data,
    )


class ImportRequest(BaseModel):
    key: str = ""
    full_key: str = ""
    auth_key: str = ""
    url: str = ""

    def get_key(self) -> str:
        """Единая точка получения ключа (поддерживает все варианты полей фронта)."""
        return (self.key or self.full_key or self.auth_key).strip()


def _source_label(platform: str) -> str:
    """Каноническая метка источника импорта из файла."""
    cfg = PLATFORM_CONFIG.get(platform) or {}
    return f"{cfg.get('name', platform)} (Файл)"


def _parse_yandex_api_credentials(raw_key: str) -> tuple[str, str] | None:
    """
    Разбирает строку ключа Яндекс Маркета.
    Поддерживаемые форматы:
      - 'yandex:217055223:ACMA:...'
      - '217055223:ACMA:...'
      - 'yandex:ACMA:...' (business_id берётся из YANDEX_BUSINESS_ID в .env)
      - 'ACMA:...'        (business_id берётся из YANDEX_BUSINESS_ID в .env)
    Возвращает (business_id, api_token) или None, если это не ключ Яндекса.
    """
    s = raw_key.strip()
    if s.lower().startswith("yandex:"):
        s = s[7:].strip()

    default_biz_id = os.getenv("YANDEX_BUSINESS_ID", "217055223").strip()

    # Вариант 1: сразу начинается с ACMA: или y0_
    if s.startswith(("ACMA:", "y0_")):
        if not default_biz_id:
            raise ValueError(
                "Укажите ID кабинета перед ключом через двоеточие: 'businessId:ACMA:...'"
            )
        return default_biz_id, s

    # Вариант 2: '<business_id>:<token>' (где token может быть 'ACMA:...:...')
    if ":" in s:
        first, rest = s.split(":", 1)
        if first.strip().isdigit() and (rest.startswith(("ACMA:", "y0_")) or len(rest) > 15):
            return first.strip(), rest.strip()

    return None


# ==================== ПРЕДПРОСМОТР ФАЙЛА ====================
@limiter.limit("30/minute")
@router.post("/import/preview")
async def preview_import(
    request: Request,
    platform: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Предпросмотр файла: первые строки + ошибки парсинга (без записи в БД)."""
    if platform not in PLATFORM_CONFIG:
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform}")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")

    fname_lower = file.filename.lower()
    if not (fname_lower.endswith(".csv") or fname_lower.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .csv и .xlsx")
    file_type = "csv" if fname_lower.endswith(".csv") else "xlsx"

    try:
        contents = await file.read()
        if len(contents) > MAX_IMPORT_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 15 МБ)")
        preview_data = await asyncio.to_thread(
            preview_file, contents, platform, file_type, max_rows=10
        )
        return {"success": True, "preview": preview_data}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка предпросмотра: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# ==================== ИМПОРТ ПО КЛЮЧУ / YML / МОК ====================
@limiter.limit("10/minute;100/day")
@router.post("/import")
async def import_products(
    request: Request,
    payload: ImportRequest,
    current_user: User = Depends(get_current_user),
):
    """Импорт по API-ключу, мок-ключу или YML-ссылке."""
    t0 = time.perf_counter()
    auth_key = payload.get_key()

    if not auth_key:
        raise HTTPException(status_code=400, detail="Не указан API-ключ или YML-ссылка")

    # Если передан префикс вида "yandex:https://...", отделяем платформу от ссылки
    if ":" in auth_key and not auth_key.startswith(("http://", "https://")):
        prefix, rest = auth_key.split(":", 1)
        if prefix.lower() in PLATFORM_CONFIG and rest.startswith(("http://", "https://")):
            auth_key = rest.strip()

    is_mock = auth_key.lower() in (
        "test:test",
        "mock_wb_key",
        "mock_ozon_key",
        "mock_yandex_key",
    ) or auth_key.lower().endswith(
        (":test:test", ":mock_wb_key", ":mock_ozon_key", ":mock_yandex_key")
    )

    # ---------- 1. Мок-импорт (для демо и тестов) ----------
    if is_mock:
        if "yandex" in auth_key.lower():
            platform = "yandex"
        elif "wb" in auth_key.lower() or "wildberries" in auth_key.lower():
            platform = "wildberries"
        else:
            platform = "ozon"

        # P-2: мок-товары идут через общий пакетный путь bulk_import
        mock_products = [
            {
                "name": "Швабра с отжимом и ведром, самоочищающаяся, 2 насадки, 10 л",
                "price": 899.0,
                "description": "<p>Удобная швабра с ведром для быстрой уборки.</p>",
                "category": "Дом и сад > Уборка > Швабры",
                "photos": [
                    f"https://mock.local/{platform}/mop/{i}.jpg" for i in range(1, 4)
                ],
            },
            {
                "name": "Смартфон Xiaomi Redmi Note 12 4/128GB",
                "price": 12990.0,
                "description": "Отличный смартфон с хорошей камерой.",
                "category": "Электроника > Смартфоны",
                "photos": [
                    f"https://mock.local/{platform}/phone/{i}.jpg" for i in range(1, 6)
                ],
            },
            {
                "name": "Чай черный байкальский, 100 пакетиков",
                "price": 250.0,
                "description": "Натуральный черный чай.",
                "category": "Продукты питания > Чай и кофе > Чай",
                "photos": ["https://mock.local/market/tea/1.jpg"],
            },
        ]

        source_label = f"{PLATFORM_CONFIG[platform]['name']} (тест)"
        imported_count, _ = await asyncio.to_thread(
            _persist_imported_products, current_user.id, source_label, "create", mock_products
        )

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

    # ---------- 2. YML-фид (Яндекс Маркет по ссылке) ----------
    if auth_key.startswith(("http://", "https://")):
        try:
            yml_result = YmlParser().fetch_and_parse(auth_key)
            yml_products = (
                yml_result.get("offers", []) if isinstance(yml_result, dict) else yml_result
            )
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
                total_rows=0,
                imported=0,
                updated=0,
                failed=0,
                errors=[{"error": f"Ошибка парсинга YML: {str(e)}"}],
            )
            stats_repo.record(
                user_id=current_user.id,
                operation="import_yml",
                platform="yandex",
                status="error",
                total_items=0,
                success_items=0,
                failed_items=0,
                duration_ms=duration_ms,
            )
            raise HTTPException(status_code=400, detail=f"Ошибка парсинга YML: {e}")

        if not yml_products:
            raise HTTPException(status_code=400, detail="Не найдено товаров в YML-фиде")

        # P-2: пакетная запись через общий bulk-путь (одна сессия, чанк-коммиты)
        yml_rows = []
        for p_data in yml_products:
            photos = p_data.get("photos") or []
            params = p_data.get("params") or {}
            yml_rows.append(
                {
                    "name": p_data.get("name", "Без названия"),
                    "price": float(p_data.get("price", 0)),
                    "description": p_data.get("description", ""),
                    "photos": photos,
                    "category": p_data.get("category", "Не указана"),
                    "sku": p_data.get("offer_id") or p_data.get("sku"),
                    "external_id": p_data.get("external_id"),
                    "brand": p_data.get("vendor") or p_data.get("brand"),
                    "attributes": (
                        [{"name": k, "value": str(v)} for k, v in params.items() if k and v]
                        if isinstance(params, dict)
                        else []
                    ),
                }
            )

        imported_count, _ = await asyncio.to_thread(
            _persist_imported_products,
            current_user.id,
            "Яндекс Маркет (YML)",
            "create",
            yml_rows,
        )

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

    # ---------- 3. Реальный API Яндекс Маркета (ACMA:... / businessId:ACMA:...) ----------
    try:
        ym_creds = _parse_yandex_api_credentials(auth_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if ym_creds:
        business_id, api_token = ym_creds
        try:
            connector = YandexSellerConnector(business_id=business_id, api_token=api_token)
            ym_offers = await connector.get_products(limit=200)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Ошибка импорта через API Яндекс Маркета: {e}")
            raise HTTPException(status_code=502, detail=f"Ошибка API Яндекс Маркета: {e}")

        if not ym_offers:
            raise HTTPException(
                status_code=400,
                detail=f"В кабинете Яндекс Маркета (businessId={business_id}) не найдено товаров",
            )

        # P-2: пакетная запись через общий bulk-путь
        ym_rows = []
        for p_data in ym_offers:
            photos = p_data.get("photos") or []
            ym_rows.append(
                {
                    "name": p_data.get("name", "Без названия"),
                    "price": float(p_data.get("price") or 0),
                    "description": p_data.get("description", ""),
                    "photos": photos,
                    "category": p_data.get("category", "Не указана"),
                    "sku": p_data.get("sku"),
                    "external_id": p_data.get("external_id"),
                    "brand": p_data.get("brand"),
                    "barcode": p_data.get("barcode"),
                    "package_weight_grams": p_data.get("package_weight_grams"),
                    "package_length_mm": p_data.get("package_length_mm"),
                    "package_width_mm": p_data.get("package_width_mm"),
                    "package_height_mm": p_data.get("package_height_mm"),
                    "okpd_code": p_data.get("okpd_code"),
                }
            )

        imported_count, _ = await asyncio.to_thread(
            _persist_imported_products,
            current_user.id,
            "Яндекс Маркет (API)",
            "create",
            ym_rows,
        )

        duration_ms = int((time.perf_counter() - t0) * 1000)
        op_log.log_file_operation(
            user_id=current_user.id,
            operation="import_api",
            platform="yandex",
            filename=f"businessId:{business_id}",
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

    # ---------- 4. Остальные API площадок ----------
    return {
        "success": False,
        "imported": 0,
        "updated": 0,
        "platform_name": "Неизвестно",
        "is_mock": False,
        "detail": (
            "Для Яндекс Маркета укажите ключ в формате '217055223:ACMA:...' или YML-ссылку. "
            "Для демо-режима используйте 'test:test'."
        ),
    }


# ==================== ИМПОРТ ИЗ ФАЙЛА (XLSX / CSV) ====================
@limiter.limit("10/minute;100/day")
@router.post("/import/file")
async def import_from_file(
    request: Request,
    platform: str = Form(...),
    mode: str = Form("create"),  # create | upsert
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Импорт товаров из Excel (.xlsx) или CSV.
    mode=upsert — обновляет существующие карточки по external_id/sku вместо дублей.
    Варианты (SKU) и характеристики (attributes) из файла сохраняются в связанные таблицы.
    """
    t0 = time.perf_counter()

    if platform not in PLATFORM_CONFIG:
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform}")
    if mode not in ("create", "upsert"):
        raise HTTPException(status_code=400, detail="Режим должен быть create или upsert")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")

    fname_lower = file.filename.lower()
    if not (fname_lower.endswith(".csv") or fname_lower.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .csv и .xlsx")
    file_type = "csv" if fname_lower.endswith(".csv") else "xlsx"

    # ---------- Парсинг ----------
    try:
        contents = await file.read()
        if len(contents) > MAX_IMPORT_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 15 МБ)")
        # openpyxl — CPU-bound, выносим в threadpool, чтобы не блокировать event loop (B-1)
        result = await asyncio.to_thread(parse_file, contents, platform, file_type)
    except HTTPException:
        raise
    except ValueError as e:
        stats_repo.record(
            user_id=current_user.id,
            operation="import_file",
            platform=platform,
            status="error",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка парсинга файла: {e}")
        stats_repo.record(
            user_id=current_user.id,
            operation="import_file",
            platform=platform,
            status="error",
            duration_ms=int((time.perf_counter() - t0) * 1000),
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
            imported=0,
            updated=0,
            failed=len(errors),
            errors=errors[:10],
        )
        stats_repo.record(
            user_id=current_user.id,
            operation="import_file",
            platform=platform,
            status="error",
            total_items=result["total_rows"],
            success_items=0,
            failed_items=len(errors),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise HTTPException(
            status_code=400, detail="Не найдено валидных товаров в файле. Проверьте ошибки."
        )

    # ---------- Запись в БД ----------
    # Синхронные repo-записи вынесены в threadpool: event loop не блокируется
    # на время записи сотен товаров (B-1, неделя 2)
    source_label = _source_label(platform)
    imported, updated = await asyncio.to_thread(
        _persist_imported_products, current_user.id, source_label, mode, products_data
    )

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