# Last Updated : 2026-09-02

"""관리자 화면 고객 조회·추가·수정·탈퇴. /api/customers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.api.schemas import CustomerUpdate, SignupRequest
from app.core.db import get_db
from app.services.customers import (
    create_customer,
    customer_detail,
    customer_list,
    update_customer,
    withdraw_customer,
)
from app.services.searching import similar_reviews_for
from app.services.strategy import generate_strategy

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/api/customers")
def list_customers(db: Session = Depends(get_db)):
    return customer_list(db)


@router.get("/api/customers/{user_id}")
def get_customer(user_id: int, db: Session = Depends(get_db)):
    detail = customer_detail(db, user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    return detail


@router.post("/api/customers", status_code=201)
def add_customer(payload: SignupRequest, db: Session = Depends(get_db)):
    """회원 추가 - 회원가입과 같은 바디. 이메일이 이미 있으면 409. 만든 고객의 상세를 돌려준다."""
    return create_customer(db, payload.model_dump())


@router.patch("/api/customers/{user_id}")
def edit_customer(user_id: int, patch: CustomerUpdate, db: Session = Depends(get_db)):
    """준 필드만 고치고 고친 뒤의 상세를 돌려준다. pet_* 를 고치려면 pet_id 도 준다."""
    return update_customer(db, user_id, patch.model_dump(exclude_unset=True))


@router.delete("/api/customers/{user_id}", status_code=204)
def remove_customer(user_id: int, db: Session = Depends(get_db)):
    """탈퇴 처리. 행은 남고(구매 이력 보존) 목록·로그인에서만 빠진다."""
    withdraw_customer(db, user_id)


@router.get("/api/customers/{user_id}/similar-reviews")
def customer_similar_reviews(user_id: int, db: Session = Depends(get_db)):
    """이 고객의 최근 리뷰를 근거로 한 상품 추천. 구매 이력이 없으면 빈 목록."""
    return similar_reviews_for(db, user_id)


@router.post("/api/customers/{user_id}/strategy")
def customer_strategy(user_id: int, db: Session = Depends(get_db)):
    """구매이력 기반 판매전략/CS 응대안. citations 각각에 실제 이 고객 구매인지 대조한 verified가 붙는다."""
    result = generate_strategy(db, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="구매 이력이 없어 전략을 생성할 수 없습니다.")
    return result
