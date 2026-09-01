# Last Updated : 2026-09-01

"""관리자 화면 고객 조회. GET /api/customers, GET /api/customers/{user_id}."""

from fastapi import APIRouter, HTTPException

from app.repositories import users as users_repo

router = APIRouter()


@router.get("/api/customers")
def list_customers():
    return users_repo.list_users()


@router.get("/api/customers/{user_id}")
def customer_detail(user_id: int):
    detail = users_repo.get_user_detail(user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    return detail
