# Last Updated : 2026-08-31

""" /recommend POST 엔드포인트 하나 — 요청을 받아 
    profile.build_profile() → searching.candidates() → recommending.recommend() 순서로 엮고 RecommendResponse로 돌려준다.
"""

from fastapi import APIRouter, HTTPException
from app.api.schemas import RecommendRequest,RecommendResponse
from app.features.profile import build_profile
from app.features.searching import candidates
from app.features.recommending import recommend

router = APIRouter()

@router.post("/recommend", response_model=RecommendResponse)
def recommend_route(req: RecommendRequest) -> RecommendResponse:
    """profile 구성 -> 후보 검색 -> LLM 추천 순서로 엮는다."""
    profile = build_profile(req.model_dump())
    matches = candidates(profile,req.user_query)
    if not matches:
        raise HTTPException(404,"조건에 맞는 후보를 찾지 못했습니다.")

    picks, retries, error = recommend(matches, profile, req.n_pick)
    return RecommendResponse(picks=picks, retries=retries, error=error)
