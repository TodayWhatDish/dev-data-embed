# Last Updated : 2026-09-03

"""로그인 회원 본인 구매내역/리뷰. user_id는 토큰에서만 가져온다 - /me/pets와 같은 이유
(다른 회원 구매를 user_id만 바꿔서 못 보게)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import BuyRequest, ReviewRequest
from app.core.auth import get_current_user
from app.features.purchases import buy, my_purchases, write_review

router = APIRouter()


@router.get("/me/purchases")
def my_purchases_route(user_id: int = Depends(get_current_user)) -> list[dict]:
    """로그인한 회원 본인의 구매 내역. 리뷰를 쓴 건이면 rating/review_body가 같이 온다."""
    return my_purchases(user_id)


@router.post("/me/purchases", status_code=201)
def buy_route(payload: BuyRequest, user_id: int = Depends(get_current_user)) -> dict:
    """추천 카드에서 '구매하기' - 실제 purchase 행을 만든다. 반려동물이 없거나 없는
    상품이면 409."""
    try:
        purchase_id = buy(user_id, payload.product_id, payload.quantity)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"purchase_id": purchase_id}


@router.post("/me/purchases/{purchase_id}/review", status_code=201)
def write_review_route(purchase_id: int, payload: ReviewRequest,
                        user_id: int = Depends(get_current_user)) -> dict:
    """본인 구매 건에 리뷰를 남긴다. 남의 구매거나 이미 리뷰가 있으면 409."""
    try:
        write_review(user_id, purchase_id, payload.rating, payload.body)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True}
