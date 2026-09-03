# Last updated: 2026-09-03
# Last Updated : 2026-09-03

"""일반 회원 가입/로그인 엔드포인트. admin_auth.py 라우트와 같은 모양."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import AuthResponse, LoginRequest, SignupRequest
from app.core.auth import get_current_user
from app.features.auth import login, signup

router = APIRouter()


@router.post("/signup", response_model=AuthResponse)
def signup_route(payload: SignupRequest) -> AuthResponse:
    """회원가입. 이메일이 이미 있으면 409, 성공하면 로그인과 동일하게 바로 토큰을 발급한다."""
    try:
        token = signup(
            payload.email, payload.password, payload.name, payload.pet_name,
            phone=payload.phone, region=payload.region,
            pet_gender=payload.pet_gender, pet_birth_date=payload.pet_birth_date,
            pet_weight_kg=payload.pet_weight_kg,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return AuthResponse(access_token=token)


@router.post("/login", response_model=AuthResponse)
def login_route(payload: LoginRequest) -> AuthResponse:
    """일반 회원 로그인. 이메일/비밀번호가 안 맞으면 401."""
    try:
        token = login(payload.email, payload.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    return AuthResponse(access_token=token)


@router.get("/me", dependencies=[Depends(get_current_user)])
def me() -> dict:
    """토큰이 유효한지 화면에서 확인할 때."""
    return {"role": "user"}
