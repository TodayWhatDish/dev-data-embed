# Last Updated : 2026-09-02

""" 정형 필터(SQL)가 먼저 거르고 LLM은 그 후보 위에서만 판단"을 실행하는 자리.
    이게 없으면 LLM에 상품 전체를 넘기게 돼서 토큰 낭비 + 축종/알러지 안 맞는 후보까지 섞여 들어감.

    DB 에는 repositories 를 통해서만 닿는다. 여기서 테이블 이름을 알 필요가 없다 —
    features/products.py 가 이미 그 모양이라 결을 맞춘다.
"""
import logging
from typing import Any

from app.core.config import PASSAGE_PREFIX
from app.domain.products import root_category_name
from app.features.retrieve import build_where
from app.features.profile import pet_profile
from pipeline.vector_db import search,connect
from app.repositories import products as product_repo
from app.repositories import purchases as purchase_repo
from app.features.customers import customer_detail
logger = logging.getLogger()



def candidates(profiles: dict[str, Any],user_query: str, limit: int=20) -> list[dict[str, Any]]:
    """ 프로필에 맞는 상품 후보를 반환한다.

        별점/알레르기/체급/축종 필터는 build_where()가 이미 SQL로 처리한다.
        여기서는 리뷰 단위의 결과를 product 테이블과 합쳐 LLM이 판단할 수 있는 모양으로 바꾼다.
    """
    con = connect()
    try:
        where, params = build_where(profiles)
        hits = search(con, user_query, where=where, params=params, top_k=limit)
        logger.debug(f"벡터 검색 {len(hits)}건 (top_k={limit}, params={params})")
    except Exception:
        # 무엇이 터졌든 질문과 프로필은 남긴다 - 이게 없으면 어떤 입력에서 죽었는지 못 찾는다
        logger.exception(f"벡터 검색 실패: query={user_query!r}, profiles={profiles}")
        raise
    finally:
        # 원래는 return 직전에만 닫아서, 중간에 터지면 커넥션이 샜다. finally 라야 반드시 닫힌다
        con.close()

    result = []
    for purchase_id, score, review in hits:
        # 색인은 purchase 단위인데 보여줄 건 product 라 한 단계 건너뛴다.
        # 조회 실패는 예외가 아니라 None 이다 (repositories 규약) - 그 건만 빼고 검색은 살린다
        product_id = purchase_repo.get_product_id(purchase_id)
        if product_id is None:
            logger.warning(f"색인이 가리키는 purchase_id={purchase_id} 가 없다 - 후보에서 제외")
            continue

        product = product_repo.find_by_id(product_id)
        if product is None:
            logger.warning(f"purchase_id={purchase_id} 의 product_id={product_id} 가 없다 - 후보에서 제외")
            continue

        result.append({
            "product_id": product_id,
            "name": product["name"],
            "brand": product["brand"],
            "price_krw": product["price_krw"],
            "product_type": root_category_name(product["product_category_id"]),  # 사료/간식
            "score": score,
            "review": review.removeprefix(PASSAGE_PREFIX),
        })

    dropped = len(hits) - len(result)
    if dropped:
        logger.warning(f"검색 {len(hits)}건 중 {dropped}건이 상품 조회에 실패해 빠졌다")
    logger.info(f"후보 {len(result)}건 반환 (검색 {len(hits)}건)")
    return result
def similar_reviews_for(user_id: int, limit: int = 5) -> dict[str, Any]:
    """이 고객이 실제로 남긴 가장 최근 리뷰를 쿼리 삼아 추천을 찾는다.

    admin이 임의로 친 질문이 아니라 이 고객의 구매 이력 자체가 근거다.
    이미 산 그 상품은 결과에서 뺀다 - 방금 산 걸 또 추천하면 의미가 없다.
    """
    detail = customer_detail(user_id)
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
