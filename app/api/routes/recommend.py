# Last Updated : 2026-08-31

""" /recommend POST 엔드포인트 하나 — 요청을 받아 
    profile.build_profile() → searching.candidates() → recommending.recommend() 순서로 엮고 RecommendResponse로 돌려준다.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.api.schemas import RecommendRequest,RecommendResponse
from app.core.auth import get_current_user
from app.features.profile import build_profile, pet_profile, survey_query_text
from app.features.searching import candidates
from app.features.recommending import recommend
from app.repositories.pet import find_pets_by_user

router = APIRouter()

@router.post("/recommend", response_model=RecommendResponse)
def recommend_route(req: RecommendRequest) -> RecommendResponse:
    """profile 구성 -> 후보 검색 -> LLM 추천 순서로 엮는다."""
    profile = build_profile(req.model_dump())
    matches = candidates(profile,req.user_query)
    if not matches:
        raise HTTPException(404,"조건에 맞는 후보를 찾지 못했습니다.")

    picks, retries, error = recommend(matches, profile, req.n_pick)
    return RecommendResponse(
        picks=picks,
        retries=retries,
        error=error)


@router.get("/me/recommend")
def my_recommend(user_id: int = Depends(get_current_user)) -> dict:
    """로그인 직후 첫 화면용 추천 - 가입 설문(알러지/식성/피부) 기준.
    로그인마다 불릴 수 있어 LLM(recommend())은 안 태우고 벡터 검색 후보까지만 준다."""
    pets = find_pets_by_user(user_id)
    if not pets:
        return {"query": "", "found": []}

    pet_id = pets[0]["pet_id"]
    profile = pet_profile(pet_id)
    query_text = survey_query_text(pet_id)
    return {"query": query_text, "found": candidates(profile, query_text, limit=5)}
