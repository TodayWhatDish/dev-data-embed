# Last updated: 2026-09-03
# Last Updated : 2026-09-03

"""일반 회원 가입/로그인 엔드포인트. admin_auth.py 라우트와 같은 모양."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import AuthResponse, LoginRequest, SignupRequest
from app.core.auth import get_current_user
from app.domain.common import CommonMgr
from app.domain.pet import attach_names
from app.services.auth import login, signup
from app.services.customers import customer_detail
from app.repositories.pet import find_pets_by_user

router = APIRouter()


@router.post("/signup", response_model=AuthResponse)
def signup_route(payload: SignupRequest) -> AuthResponse:
    """회원가입. 이메일이 이미 있으면 409, 성공하면 로그인과 동일하게 바로 토큰을 발급한다."""
    try:
        token = signup(
            payload.email,
            payload.password,
            payload.name,
            payload.pet_name,
            phone=payload.phone,
            region=payload.region,
            pet_species=payload.pet_species,
            pet_gender=payload.pet_gender,
            pet_birth_date=payload.pet_birth_date,
            pet_weight_kg=payload.pet_weight_kg,
            pet_size=payload.pet_size,
            pet_activity_level=payload.pet_activity_level,
            pet_allergies=payload.pet_allergies,
            diet_note=payload.diet_note,
            skin_note=payload.skin_note,
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
    /ask/me와 같은 이유(다른 회원 펫을 user_id만 바꿔서 못 보게).
    animal_category_id -> animal_category 이름 변환은 attach_names()로 한다 (services/profile.py와 동일)."""
    return attach_names(find_pets_by_user(user_id))


@router.get("/me/profile")
def my_profile(user_id: int = Depends(get_current_user)) -> dict:
    """마이페이지: 내 프로필 + 펫 상세(품종/체중/알레르기 등) + 구매이력을 한 번에.
    관리자 고객상세(GET /api/customers/{user_id})가 쓰는 customer_detail()을 그대로 재사용한다 -
    본인 데이터라 마스킹도 필요 없고, 같은 내용을 또 쿼리할 이유가 없다."""
    detail = customer_detail(user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="회원 정보를 찾을 수 없습니다.")
    return detail


@router.get("/allergens")
def allergens() -> list[str]:
    """회원가입 폼의 알레르기 체크박스 목록. 기동 시 캐시된 마스터를 그대로 돌려준다 -
    DB를 또 안 친다(app/api/lifespan.py의 load_domain_cache)."""
    return CommonMgr.get_inst().get_allergen_names()
