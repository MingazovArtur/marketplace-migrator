"""
Роутер для авто-подбора и поиска кодов ТН ВЭД.
"""
from fastapi import APIRouter, Query
from services.tnved_mapper import suggest_tnved, search_tnved

router = APIRouter(prefix="/api/tnved", tags=["ТН ВЭД"])


@router.get("/suggest")
def suggest_tnved_endpoint(
    name: str = Query(..., description="Название товара для анализа"),
    category: str = Query("", description="Категория товара (опционально)")
):
    """
    Авто-подбор кодов ТН ВЭД на основе названия и категории.
    Возвращает топ-3 наиболее вероятных варианта.
    """
    suggestions = suggest_tnved(name, category)
    
    return {
        "success": True,
        "suggestions": suggestions,
        "message": f"Найдено {len(suggestions)} вариантов" if suggestions else "Точных совпадений не найдено. Проверьте название или категорию."
    }


@router.get("/search")
def search_tnved_endpoint(
    query: str = Query(..., min_length=2, description="Поисковый запрос (слово, часть кода или описание)")
):
    """
    Поиск по справочнику ТН ВЭД по произвольному запросу.
    Возвращает до 10 релевантных записей.
    """
    results = search_tnved(query)
    
    return {
        "success": True,
        "results": results,
        "total": len(results)
    }