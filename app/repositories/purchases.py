# Last Updated : 2026-09-01

"""purchase 테이블에 닿는 자리. 구매 단건 조회만 있다."""

from app.core.db import one

def get_product_id(purchase_id: int) -> int:
    """이 구매가 산 상품의 id"""
    return one("SELECT product_id FROM purchase WHERE purchase_id = ?",(purchase_id,))[0]

def count_for_product(product_id: int) -> int:
    """이 상품이 몇 번 팔렸는지"""
    return one("SELECT COUNT(*) FROM purchase WHERE product_id = ?",(product_id,))[0]