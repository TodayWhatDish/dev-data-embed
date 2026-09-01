# Last updated: 2026-09-01

""" 관리자 대시보드에서 상품을 등록/수정/삭제할 자리.

    검색/추천 후보를 고르는 로직(candidates())은 features/searching.py로 옮겼다.
    CRUD와 검색은 서로 다른 이유로 바뀌는 코드라 한 파일에 안 섞는다.
"""

from app.repositories import products as product_repo
from app.repositories import purchases as purchase_repo

class ProductError(Exception):
    """상품 관련 오류 : CRUD가 거부한 이유로 routes가 HTTP 상태로 옮긴다."""
    def __init__(self, kind:str, message:str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def list_products(page:int, size:int) -> list[dict]:
    """상품 여러 건 조회"""
    return product_repo.find_page(page,size)

def get_product(product_id:int) -> dict:
    """상품 한 건 조회"""
    product = product_repo.find_by_id(product_id)
    if not product:
        raise ProductError("not_found",f"product_id {product_id}상품이 없다.")
    return product

def create_product(values:dict) -> dict:
    """등록하고, 등록된 걸 다시 조회해서 돌려준다."""
    product_id = product_repo.insert(values)
    return product_repo.find_by_id(product_id)

def update_product(product_id:int, values:dict) -> dict:
    """없으면 ProductError를 raise 하고, 있으면 수정하고 다시 조회해서 돌려준다."""
    if product_repo.find_by_id(product_id) is None:
        raise ProductError("not_found",f"{product_id}상품이 없다.")

    product_repo.update(product_id,values)
    return product_repo.find_by_id(product_id)

def delete_product(product_id:int) -> None:
    """구매 이력이 있으면 ProductError로 막는다."""
    if product_repo.find_by_id(product_id) is None:
        raise ProductError("not_found",f"{product_id}상품이 없다.")

    used = purchase_repo.count_for_product(product_id)
    if used : 
        raise ProductError("conflict", f"구매 이력이 {used}건 있어 지울 수 없다")
    
    product_repo.delete(product_id)
