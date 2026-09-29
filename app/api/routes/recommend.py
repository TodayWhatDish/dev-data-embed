# Last Updated : 2026-08-31

"""/recommend POST 엔드포인트 하나 — 요청을 받아
profile.build_profile() → searching.candidates() → recommending.recommend() 순서로 엮고 RecommendResponse로 돌려준다.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import RecommendRequest, RecommendResponse
from app.core.db import get_db
from app.services.profile import build_profile, pet_profile, primary_pet, survey_notes, survey_queries
from app.services.recommending import recommend
from app.services.searching import candidates, candidates_for_queries

router = APIRouter()


@router.post("/recommend", response_model=RecommendResponse)
def recommend_route(rreq: RecommendRequest, db: Session = Depends(get_db)) -> RecommendResponse:
    """profile 구성 -> 후보 검색 -> LLM 추천 순서로 엮는다."""
    profile = build_profile(rreq.model_dump())
    matches = candidates(db, profile, rreq.user_query)

    if not matches:
        raise HTTPException(404, "조건에 맞는 후보를 찾지 못했습니다.")

    picks, retries, error = recommend(matches, profile, rreq.n_pick)
    return RecommendResponse(picks=picks, retries=retries, error=error)


@router.get("/me/recommend")
def my_recommend(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """로그인 직후 첫 화면용 추천 - 가입 설문(알러지/식성/피부) 기준.
    로그인마다 불릴 수 있어 LLM(recommend())은 안 태우고 벡터 검색 후보까지만 준다."""
    pet = primary_pet(db, user_id)
    if pet is None:
        return {"query": "", "found": []}

    pet_id = pet["pet_id"]
    profile = pet_profile(db, pet_id)
    notes = survey_notes(db, pet_id)
    # query 는 화면의 '이 조건으로 골랐어요' 칩용 - 실제 검색은 메모별 질의로 한다
    return {"query": " ".join(notes), "found": candidates_for_queries(db, profile, survey_queries(notes), limit=5)}
