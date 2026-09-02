# Last Updated : 2026-08-31

""" 정형 필터(SQL)가 먼저 거르고 LLM은 그 후보 위에서만 판단"을 실행하는 자리. 
    이게 없으면 LLM에 상품 전체를 넘기게 돼서 토큰 낭비 + 축종/알러지 안 맞는 후보까지 섞여 들어감.
"""
from typing import Any
from app.core.config import PASSAGE_PREFIX
from app.features.retrieve import build_where
from app.core.db import fetch_tuples
from app.features.profile import pet_profile
from app.repositories import users as users_repo
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
        product_id = fetch_tuples(
            "SELECT product_id FROM purchase WHERE purchase_id = ?", (purchase_id,)
        )[0][0]
        name, brand, price = fetch_tuples(
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


def similar_reviews_for(user_id: int, limit: int = 5) -> dict[str, Any]:
    """이 고객이 실제로 남긴 가장 최근 리뷰를 쿼리 삼아 추천을 찾는다.

    admin이 임의로 친 질문이 아니라 이 고객의 구매 이력 자체가 근거다.
    이미 산 그 상품은 결과에서 뺀다 - 방금 산 걸 또 추천하면 의미가 없다.
    """
    detail = users_repo.get_user_detail(user_id)
    if detail is None:
        return {"query": "", "product_name": "", "found": []}

    reviewed = [p for p in detail["purchases"] if p["review_body"]]
    if not reviewed:
        return {"query": "", "product_name": "", "found": []}

    latest = reviewed[0]  # get_user_detail이 이미 purchased_at DESC로 정렬해서 준다
    profile = pet_profile(detail["pets"][0]["pet_id"]) if detail["pets"] else {}

    found = [c for c in candidates(profile, latest["review_body"], limit=limit + 1)
             if c["product_id"] != latest["product_id"]][:limit]
    return {"query": latest["review_body"], "product_name": latest["product_name"], "found": found}

