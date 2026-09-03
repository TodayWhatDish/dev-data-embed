# Last Updated : 2026-09-03

"""purchase/review 테이블에 닿는 자리. 구매 조회 + 본인 구매 리뷰 작성."""

import logging
import sqlite3
from datetime import datetime

from app.core.db import fetch, fetch_tuple_one
from app.repositories.general_query import select
from app.repositories.general_query.insert import insert_query

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

def list_by_user(user_id: int) -> list[dict]:
    """이 회원의 구매 내역 전체. 리뷰를 쓴 건이면 rating/review_body가 같이 붙는다(없으면 NULL)."""
    return fetch("""
        SELECT pu.purchase_id, pu.purchased_at, p.product_id, p.name AS product_name,
               r.rating, r.body AS review_body
        FROM purchase AS pu
        JOIN pet AS pe ON pe.pet_id = pu.pet_id
        JOIN product AS p ON p.product_id = pu.product_id
        LEFT JOIN review AS r ON r.purchase_id = pu.purchase_id
        WHERE pe.user_id = ?
        ORDER BY pu.purchased_at DESC
    """, (user_id,))

def is_owned_by(purchase_id: int, user_id: int) -> bool:
    """이 구매가 이 회원 것인지. 리뷰를 쓰기 전에 남의 구매를 못 건드리게 막는다."""
    rows = fetch("""
        SELECT 1 FROM purchase AS pu JOIN pet AS pe ON pe.pet_id = pu.pet_id
        WHERE pu.purchase_id = ? AND pe.user_id = ?
    """, (purchase_id, user_id))
    return bool(rows)

def create_purchase(pet_id: int, product_id: int, quantity: int, unit_price_krw: int) -> int:
    """구매 한 건을 남긴다. age_month_at_purchase/size_at_purchase는 지금 계산할 근거가
    마땅치 않아 비운다(둘 다 NULL 허용 컬럼)."""
    return insert_query("purchase", {
        "pet_id": pet_id,
        "product_id": product_id,
        "quantity": quantity,
        "unit_price_krw": unit_price_krw,
        "purchased_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

def create_review(purchase_id: int, rating: int, body: str) -> None:
    """구매 건에 리뷰를 남긴다. purchase_id가 review의 PK라 이미 리뷰가 있으면
    QueryError('constraint_unique')가 난다 - 부르는 쪽(features)이 잡는다."""
    insert_query("review", {
        "purchase_id": purchase_id,
        "rating": rating,
        "body": body,
        "reviewed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
