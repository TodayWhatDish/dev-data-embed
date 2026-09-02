# Last Updated : 2026-09-01

"""관리자 대시보드 - 상품 CRUD API. 전부 관리자 인증이 필요하다."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import Product, ProductCreate, ProductUpdate
from app.core.auth import get_current_admin
from app.features import products

router = APIRouter(prefix="/admin/products", tags=["관리자-상품"],
                   dependencies=[Depends(get_current_admin)])


def _http(exc: products.ProductError) -> HTTPException:
    """ProductError.kind를 HTTP 상태로 옮긴다."""
    status_code = 404 if exc.kind == "not_found" else 409
    return HTTPException(status_code=status_code, detail=exc.message)


@router.get("", response_model=list[Product])
def product_list(page: int = 0, size: int = 20):
    """전체 제품 리스트 출력(page방식)"""
    return products.list_products(page, size)


@router.get("/{product_id}", response_model=Product)
def product_get(product_id: int):
    """product_id로 제품 정보를 출력, 없으면 에러"""
    try:
        return products.get_product(product_id)
    except products.ProductError as exc:
        raise _http(exc) from exc


@router.post("", response_model=Product, status_code=201)
def product_create(draft: ProductCreate):
    """"product_id는 PK로 auto ingrement"""
    return products.create_product(draft.model_dump())


@router.patch("/{product_id}", response_model=Product)
def product_update(product_id: int, patch: ProductUpdate):
    try:
        return products.update_product(product_id, patch.model_dump(exclude_unset=True))
    except products.ProductError as exc:
        raise _http(exc) from exc


@router.delete("/{product_id}", status_code=204)
def product_delete(product_id: int):
    try:
        products.delete_product(product_id)
    except products.ProductError as exc:
        raise _http(exc) from exc

    
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
