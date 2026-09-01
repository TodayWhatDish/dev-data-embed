# Last Updated : 2026-09-01

""" /recommend POST 엔드포인트 하나 — 요청을 받아 
    profile.build_profile() → searching.candidates() → recommending.recommend() 순서로 엮고 RecommendResponse로 돌려준다.
"""

from fastapi import APIRouter, HTTPException
from app.api.schemas import Evidence, Pick, RecommendRequest,RecommendResponse
from app.features.profile import build_profile
from app.features.searching import candidates
from app.features.recommending import recommend

router = APIRouter()

@router.post("/recommend", response_model=RecommendResponse)
def recommend_route(req: RecommendRequest) -> RecommendResponse:
    """profile 구성 -> 후보 검색 -> LLM 추천 -> 근거 되붙이기 순서로 엮는다."""
    profile = build_profile(req.model_dump())
    matches = candidates(profile,req.user_query)
    if not matches:
        raise HTTPException(404,"조건에 맞는 후보를 찾지 못했습니다.")

    picks, retries, error = recommend(matches, profile, req.n_pick)

    # LLM 은 product_id 와 후기 ID 만 돌려준다. 화면에 필요한 이름·가격과 인용된
    # 후기 본문은 후보에서 도로 붙인다 — 모델이 옮겨 적게 하면 그 과정에서 값이 바뀐다.
    # candidates() 는 후기 한 건이 한 행이라 같은 상품이 여러 번 나온다. 상품 정보는
    # 먼저 본 것으로 두고, 후기만 상품 밑에 모은다.
    info: dict[int, dict] = {}
    reviews_of: dict[int, list[dict]] = {}
    for m in matches:
        info.setdefault(m["product_id"], m)
        reviews_of.setdefault(m["product_id"], []).append(
            {"id": m["review_id"], "rating": m["rating"], "body": m["review"]})

    enriched = []
    for pick in picks:
        c = info[pick["product_id"]]
        found = reviews_of[pick["product_id"]]
        # 후보에 없는 후기 ID 는 버린다. 모델이 지어낸 ID 를 그대로 실으면
        # 근거가 붙은 추천과 근거를 지어낸 추천을 화면에서 구분할 수 없다.
        cited = set(pick.get("evidence", [])) & {r["id"] for r in found}
        enriched.append(Pick(
            product_id=pick["product_id"],
            reason=pick["reason"],
            name=c["name"],
            brand=c["brand"],
            price_krw=c["price_krw"],
            evidence=[Evidence(**r) for r in found if r["id"] in cited],
        ))

    return RecommendResponse(picks=enriched, retries=retries, error=error,
                             searched=len(matches))
