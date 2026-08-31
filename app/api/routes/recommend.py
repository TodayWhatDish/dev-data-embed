# Last Updated : 2026-08-30

"""1 → 5 를 한 줄로 잇는 자리. 검색도 프롬프트 조립도 여기서 하지 않는다.

    요청을 프로필로 옮기고(1·2), 색인에서 유사 리뷰를 찾고(3·4), 그 결과를 후보로
    접어 LLM 에 넘긴다(5). 각 단계의 알맹이는 features/ 와 domain/ 에 있고 여기는
    순서만 안다 — 순서를 바꾸고 싶을 때 볼 파일이 하나가 되도록.
"""
from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import Evidence, Pick, RecommendRequest, RecommendResponse
from app.features import products, recommending
from app.features.retrieve import build_where
from pipeline.vector_db import search

router = APIRouter()


@router.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest, request: Request) -> RecommendResponse:
    """질문 하나를 받아 근거 붙은 추천으로 돌려준다."""
    con = request.app.state.con

    # 프로필 필터를 먼저 걸고 그 안에서 벡터 랭킹을 한다. 순서가 반대면
    # "의미만 비슷한" 대형견 리뷰가 소형견 질문의 상위에 올라온다.
    profile = {
        "animal_category": req.animal_category,
        "size_category": req.size_category,
        "allergy": req.allergy,
    }
    where, params = build_where(profile)
    hits = search(con, req.question, where=where, params=params, top_k=req.top_k)
    candidates = products.from_hits(con, hits)

    result, retries, error = recommending.recommend(
        req.question, candidates, profile, n_pick=req.n_pick)

    if result is None:
        # 재시도를 다 쓰고도 못 받았다. 지어낸 답을 내보내느니 실패로 알린다.
        raise HTTPException(status_code=502, detail=f"LLM 응답을 받지 못했습니다: {error}")

    # LLM 은 ID 만 돌려준다. 화면에 필요한 이름·가격과 인용된 후기 본문은
    # 후보에서 도로 붙인다 — 모델이 옮겨 적게 하면 그 과정에서 값이 바뀐다.
    by_id = {c["product_id"]: c for c in candidates}
    picks = []
    for pick in result["picks"]:
        c = by_id[pick["product_id"]]
        cited = {r["id"] for r in c["reviews"]} & set(pick["evidence"])
        picks.append(Pick(
            product_id=pick["product_id"],
            name=c["name"],
            brand=c["brand"],
            price_krw=c["price_krw"],
            reason=pick["reason"],
            evidence=[Evidence(id=r["id"], rating=r["rating"], body=r["body"])
                      for r in c["reviews"] if r["id"] in cited],
        ))

    return RecommendResponse(answer=result["answer"], picks=picks,
                             retries=retries, searched=len(hits))
