# Last Updated : 2026-09-02

"""관리자 화면 고객 조회. GET /api/customers, GET /api/customers/{user_id}."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_admin
from app.features.searching import similar_reviews_for
from app.features.strategy import generate_strategy
from app.repositories import users as users_repo

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/api/customers")
def list_customers():
    return users_repo.list_users()


@router.get("/api/customers/{user_id}")
def customer_detail(user_id: int):
    detail = users_repo.get_user_detail(user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    return detail


@router.get("/api/customers/{user_id}/similar-reviews")
def customer_similar_reviews(user_id: int):
    """이 고객의 최근 리뷰를 근거로 한 상품 추천. 구매 이력이 없으면 빈 목록."""
    return similar_reviews_for(user_id)


@router.post("/api/customers/{user_id}/strategy")
def customer_strategy(user_id: int):
    """구매이력 기반 판매전략/CS 응대안. citations 각각에 실제 이 고객 구매인지 대조한 verified가 붙는다."""
    result = generate_strategy(user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="구매 이력이 없어 전략을 생성할 수 없습니다.")
    return result
