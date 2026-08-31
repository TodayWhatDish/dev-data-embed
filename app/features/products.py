# Last Updated : 2026-08-30

""" 정형 필터(SQL)가 먼저 거르고 LLM은 그 후보 위에서만 판단"을 실행하는 자리. 
    이게 없으면 LLM에 상품 전체를 넘기게 돼서 토큰 낭비 + 축종/알러지 안 맞는 후보까지 섞여 들어감.
"""
import sqlite3
from typing import Any

from app.features.retrieve import fmt_product_id, fmt_purchase_id


def candidates(profiles: dict[str, Any], limit: int=20) -> list[dict[str, Any]]:
    """프로필에 맞는 상품 후보를 반환한다. (스키마 확정 전까지 pass)"""
    pass


def from_hits(con: sqlite3.Connection, hits: list[tuple]) -> list[dict[str, Any]]:
    """검색 결과(리뷰 조각)를 상품 단위 후보로 접는다.

    retrieve 가 돌려주는 한 건은 '리뷰'다. 추천해야 하는 것은 '상품'이라, 같은 상품을
    가리키는 리뷰가 여러 건 올라오면 하나로 합친다. 합치지 않고 그대로 넘기면 후보
    목록에 같은 상품이 세 번 실리고, LLM 이 그걸 서로 다른 선택지로 읽는다.

    점수는 최댓값을 쓴다. retrieve.search 가 조각을 리뷰로 접을 때 쓴 규칙과 같다 —
    '이 상품의 어느 후기 한 대목이 질문과 맞는다'가 우리가 찾는 신호이기 때문이다.

    리뷰 본문을 근거로 함께 들고 온다. LLM 이 "왜 이걸 골랐는지"를 지어내지 않고
    실제 후기에서 인용하게 하려면, 후보마다 읽을 근거가 붙어 있어야 한다.
    """
    if not hits:
        return []

    # 조회는 한 번에 끝낸다. 후보마다 따로 SELECT 하면 top_k 만큼 왕복이 생긴다.
    by_purchase = {pid: (score, doc) for pid, score, doc in hits}
    marks = ",".join("?" * len(by_purchase))
    rows = con.execute(f"""
        SELECT
            pu.purchase_id, p.product_id, p.brand, p.name, p.food_form,
            p.price_krw, p.description,
            pc_parent.name_ko AS category, pc.name_ko AS sub_category,
            GROUP_CONCAT(DISTINCT fp.name_ko) AS purposes,
            r.rating
        FROM purchase AS pu
        JOIN product AS p ON p.product_id = pu.product_id
        JOIN review AS r ON r.purchase_id = pu.purchase_id
        LEFT JOIN product_category AS pc ON pc.product_category_id = p.product_category_id
        LEFT JOIN product_category AS pc_parent ON pc_parent.product_category_id = pc.parent_id
        LEFT JOIN product_feeding_purpose AS pfp ON pfp.product_id = p.product_id
        LEFT JOIN feeding_purpose AS fp ON fp.feeding_purpose_id = pfp.feeding_purpose_id
        WHERE pu.purchase_id IN ({marks})
        GROUP BY pu.purchase_id
    """, tuple(by_purchase)).fetchall()

    folded: dict[int, dict[str, Any]] = {}
    for (purchase_id, product_id, brand, name, food_form, price, description,
         category, sub_category, purposes, rating) in rows:
        score, doc = by_purchase[purchase_id]
        # 색인 문서에 붙여둔 e5 접두어는 사람도 모델도 읽을 이유가 없다.
        evidence = doc.removeprefix("passage: ")
        seen = folded.get(product_id)
        if seen is None:
            folded[product_id] = {
                "product_id": fmt_product_id(product_id),
                "brand": brand,
                "name": name,
                "food_form": food_form,
                "price_krw": price,
                "description": description,
                "category": f"{category}/{sub_category}" if category else sub_category,
                "purposes": purposes,
                "score": score,
                "reviews": [
                    {"id": fmt_purchase_id(purchase_id), "rating": rating,
                     "score": score, "body": evidence}
                ],
            }
            continue
        seen["reviews"].append(
            {"id": fmt_purchase_id(purchase_id), "rating": rating,
             "score": score, "body": evidence})
        seen["score"] = max(seen["score"], score)

    return sorted(folded.values(), key=lambda c: -c["score"])
