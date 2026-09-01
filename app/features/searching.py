# Last Updated : 2026-08-31

""" 정형 필터(SQL)가 먼저 거르고 LLM은 그 후보 위에서만 판단"을 실행하는 자리. 
    이게 없으면 LLM에 상품 전체를 넘기게 돼서 토큰 낭비 + 축종/알러지 안 맞는 후보까지 섞여 들어감.
"""
from typing import Any
from app.core.config import PASSAGE_PREFIX
from app.features.retrieve import build_where
from app.core.db import query
from pipeline.vector_db import search,connect

def candidates(profiles: dict[str, Any],user_query: str, limit: int=20) -> list[dict[str, Any]]:
    """ 프로필에 맞는 상품 후보를 반환한다.

        별점/알레르기/체급/축종 필터는 build_where()가 이미 SQL로 처리한다.
        여기서는 리뷰 단위의 결과를 product 테이블과 합쳐 LLM이 판단할 수 있는 모양으로 바꾼다.
    """
    con = connect()
    where, params = build_where(profiles)
    hits = search(con, user_query, where=where, params=params, top_k=limit)

    result = []
    for purchase_id, score, review in hits:
        product_id = query(
            "SELECT product_id FROM purchase WHERE purchase_id = ?", (purchase_id,)
        )[0][0]
        name, brand, price = query(
            "SELECT name, brand, price_krw FROM product WHERE product_id = ?", (product_id,)
        )[0]
        result.append({
            "product_id": product_id,
            "name": name,
            "brand":brand,
            "price_krw":price,
            "score":score,
            "review": review.removeprefix(PASSAGE_PREFIX),
        })
    con.close()
    return result
    


