# Last Updated : 2026-09-02

"""purchase 테이블에 닿는 자리. 구매 단건 조회만 있다."""

import logging
import sqlite3

from app.core.db import fetch_tuple_one
from app.repositories.general_query import select

logger = logging.getLogger()

def get_product_id(purchase_id: int) -> int | None:
    """이 구매가 산 상품의 id. 없는 구매면 None.

    예전엔 fetch_tuple_one(...)[0] 이라, 없는 purchase_id 를 주면 None[0] 으로 TypeError 가 났다.
    조회에서 '없음' 은 예외가 아니라 None 이라는 규약(db.fetch_one)에 맞춘다 —
    부르는 쪽이 404 로 볼지 건너뛸지 정한다.
    """
    rows = select("purchase", {"purchase_id": purchase_id})
    return rows[0]["product_id"] if rows else None

def count_for_product(product_id: int) -> int:
    """이 상품이 몇 번 팔렸는지"""
    try:
        return fetch_tuple_one("SELECT COUNT(*) FROM purchase WHERE product_id = ?",(product_id,))[0]
    except sqlite3.Error:
        logger.exception(f"purchase 집계 실패: product_id={product_id}")
        raise
    # COUNT(*) 는 맞는 행이 없어도 (0,) 을 준다. 여기서만 [0] 이 안전한 이유다
