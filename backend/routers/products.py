from fastapi import APIRouter, HTTPException
from database.repository import repo
from models.schemas import Stats

router = APIRouter(prefix="/api", tags=["Products"])

@router.get("/products")
def get_products():
    products = repo.get_all()
    return {"total": len(products), "products": products}

@router.get("/stats", response_model=Stats)
def get_stats():
    return repo.get_stats()

@router.delete("/products/{product_id}")
def delete_product(product_id: int):
    if repo.delete(product_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Товар не найден")