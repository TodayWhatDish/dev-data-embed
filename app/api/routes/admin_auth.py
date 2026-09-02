# Last Updated : 2026-09-02

"""관리자 로그인 엔드포인트"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import AdminLoginRequest, AuthResponse
from app.core.auth import get_current_admin
from app.features.admin_auth import login

router = APIRouter()


@router.post("/admin/login", response_model=AuthResponse)
def admin_login(payload: AdminLoginRequest) -> AuthResponse:
    """관리자 로그인. 공용 비밀번호를 검증하고, 맞으면 JWT 토큰을 발급한다."""
    try:
        token = login(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    return AuthResponse(access_token=token)


@router.get("/admin/me", dependencies=[Depends(get_current_admin)])
def admin_me() -> dict:
    """토큰이 유효한지 화면에서 확인할 때."""
    return {"role": "admin"}
