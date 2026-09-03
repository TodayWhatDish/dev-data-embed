# Last updated: 2026-09-03
# Last Updated : 2026-09-03

"""일반 회원 가입/로그인 엔드포인트. admin_auth.py 라우트와 같은 모양."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import AuthResponse, LoginRequest, SignupRequest
from app.core.auth import get_current_user
from app.domain.common import CommonMgr
from app.features.auth import login, signup
from app.repositories.pet import find_pets_by_user

router = APIRouter()


@router.post("/signup", response_model=AuthResponse)
def signup_route(payload: SignupRequest) -> AuthResponse:
    """회원가입. 이메일이 이미 있으면 409, 성공하면 로그인과 동일하게 바로 토큰을 발급한다."""
    try:
        token = signup(
            payload.email, payload.password, payload.name, payload.pet_name,
            phone=payload.phone, region=payload.region, pet_species=payload.pet_species,
            pet_gender=payload.pet_gender, pet_birth_date=payload.pet_birth_date,
            pet_weight_kg=payload.pet_weight_kg, pet_size=payload.pet_size,
            pet_activity_level=payload.pet_activity_level, pet_allergies=payload.pet_allergies,
            diet_note=payload.diet_note, skin_note=payload.skin_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return AuthResponse(access_token=token)


@router.get("/allergens")
def allergens() -> list[str]:
    """회원가입 알러지 체크박스용 이름 목록. 고른 이름을 그대로 /signup의 pet_allergies로 되돌려보낸다."""
    return CommonMgr.get_inst().get_allergen_names()


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


@router.get("/me/pets")
def my_pets(user_id: int = Depends(get_current_user)) -> list[dict]:
    """로그인한 회원 본인의 펫 목록. user_id를 바디/쿼리로 안 받고 토큰에서만 가져온다 -
    /ask/me와 같은 이유(다른 회원 펫을 user_id만 바꿔서 못 보게)."""
    return find_pets_by_user(user_id)
