# Last Updated : 2026-09-01

"""관리자 로그인 엔드포인트"""

from fastapi import APIRouter, HTTPException

from app.api.schemas import AdminLoginRequest, AuthResponse
from app.features.admin_auth import login

router = APIRouter()

@router.post("/admin/login", response_model=AuthResponse)
def admin_login(payload: AdminLoginRequest) -> AuthResponse:
    """관리자 로그인. username과 password를 검증하고, 맞으면 JWT 토큰을 발급한다."""
    try:
        token = login(payload.username, payload.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    return AuthResponse(access_token=token)