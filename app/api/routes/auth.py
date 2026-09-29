# Last Updated: 2026-09-28

"""일반 회원 가입/로그인 엔드포인트. admin_auth.py 라우트와 같은 모양."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ratelimit import login_limit
from app.api.schemas import AuthResponse, LoginRequest, SignupRequest
from app.core.config import POC_ENABLED
from app.core.db import get_db
from app.domain.common import CommonMgr
from app.services.auth import login, poc_signup, signup
from app.services.customers import customer_detail
from app.services.profile import list_pets
from app.services.questions import questions_left_today

router = APIRouter()


@router.post("/signup", response_model=AuthResponse)
def signup_route(payload: SignupRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """회원가입. 이메일이 이미 있으면 409, 성공하면 로그인과 동일하게 바로 토큰을 발급한다."""
    token = signup(
        db,
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

    return AuthResponse(access_token=token)


@router.get("/allergens")
def allergens() -> list[str]:
    """회원가입 알러지 체크박스용 이름 목록. 고른 이름을 그대로 /signup의 pet_allergies로 되돌려보낸다."""
    return CommonMgr.get_inst().get_allergen_names()


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(login_limit)])
def login_route(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """일반 회원 로그인. 이메일/비밀번호가 안 맞으면 401."""
    token = login(db, payload.email, payload.password)
    return AuthResponse(access_token=token)


@router.post("/poc/login", response_model=AuthResponse, dependencies=[Depends(login_limit)])
def poc_login_route(db: Session = Depends(get_db)) -> AuthResponse:
    """시연용 원클릭 로그인. 데이터가 채워진 새 계정을 만들어 토큰을 준다. POC_ENABLED 가 아니면 없는 라우트(404)."""
    if not POC_ENABLED:
        raise HTTPException(status_code=404)
    return AuthResponse(access_token=poc_signup(db))


@router.get("/me", dependencies=[Depends(get_current_user)])
def me() -> dict:
    """토큰이 유효한지 화면에서 확인할 때."""
    return {"role": "user"}


@router.get("/me/pets")
def my_pets(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    """로그인한 회원 본인의 펫 목록. user_id를 바디/쿼리로 안 받고 토큰에서만 가져온다 -
    /ask/me와 같은 이유(다른 회원 펫을 user_id만 바꿔서 못 보게).
    이름 변환(attach_names)은 services/profile.list_pets()가 한다."""
    return list_pets(db, user_id)


@router.get("/me/profile")
def my_profile(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """마이페이지: 내 프로필 + 펫 상세(품종/체중/알레르기 등) + 구매이력을 한 번에.
    관리자 고객상세(GET /api/customers/{user_id})가 쓰는 customer_detail(db)을 그대로 재사용한다 -
    본인 데이터라 마스킹도 필요 없고, 같은 내용을 또 쿼리할 이유가 없다."""
    detail = customer_detail(db, user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="회원 정보를 찾을 수 없습니다.")
    # 새로고침해도 질문 한도가 서버 기준으로 보이게 같이 준다
    return {**detail, "questions_left": questions_left_today(db, user_id)}
