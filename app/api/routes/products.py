# Last Updated : 2026-09-01

"""관리자 화면 상품 조회/등록. GET /api/products, POST /api/products."""

from fastapi import APIRouter, Depends

from app.api.schemas import ProductCreate
from app.core.auth import get_current_admin
from app.repositories import products as products_repo

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/api/products")
def list_products():
    return products_repo.get_products()


@router.post("/api/products")
def create_product(payload: ProductCreate):
    product_id = products_repo.create_product(payload.model_dump())
    return {"product_id": product_id}
