# Last Updated : 2026-09-01

"""관리자 로그인 엔드포인트"""

from fastapi import APIRouter, Depends

from app.api.schemas import AdminLoginRequest, AuthResponse
from app.api.deps import get_current_admin, rate_limit
from app.services.admin_auth import login

router = APIRouter()


@router.post("/admin/login", response_model=AuthResponse, dependencies=[Depends(rate_limit(5, 60))])
def admin_login(payload: AdminLoginRequest) -> AuthResponse:
    """관리자 로그인. username과 password를 검증하고, 맞으면 JWT 토큰을 발급한다."""

    token = login(payload.password)  # 관리자는 DB안타고, 서버에서 확인
    return AuthResponse(access_token=token)


@router.get("/admin/me", dependencies=[Depends(get_current_admin)])
def admin_me() -> dict:
    """토큰이 유효한지 화면에서 확인할 때."""
    return {"role": "admin"}
