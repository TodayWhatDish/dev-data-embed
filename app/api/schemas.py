# Last updated: 2026-09-03
# Last Updated : 2026-08-31

"""API 요청/응답 형태를 정의하는 자리. 라우트 함수는 이 모델로 입출력을 검증한다.
들어오는 값들이 각 클래스별 클래스 변수들이 맞는지 봄.

브라우저(JS) → POST /search 요청 보냄 → FastAPI 서버가 처리 →
SearchResponse 모양으로 응답 만듦 → 그 응답이 다시 브라우저로 돌아감 →
JS가 그거 받아서 화면에 검색결과 뿌림
"""

from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

BIRTH_DATE_MIN = date(1990, 1, 1)  # pet 테이블 ck_pet_birth_date 의 하한과 같다


def _check_birth_date(v: str) -> str:
    """DB CHECK(ck_pet_birth_date)가 못 보는 두 가지를 여기서 거른다 - 달력에 없는 날(2021-02-30)과 오늘 이후.
    DB 는 TEXT 를 정규식으로만 보고, now() 기준 조건은 CHECK 에 둘 수 없다."""
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise ValueError("생년월일은 YYYY-MM-DD 형식의 실제 날짜여야 합니다.") from None
        
    # DB 의 created_at 과 같은 UTC 기준이다. 한국 날짜로 비교하면 00~09시에 DB CHECK 와 어긋난다
    today = datetime.now(timezone.utc).date()
    if not BIRTH_DATE_MIN <= d <= today:
        raise ValueError(f"생년월일은 {BIRTH_DATE_MIN} 부터 오늘까지만 받습니다.")
    return d.isoformat()


# 빈 문자열은 '미입력' 이다 - 그대로 두면 DB CHECK 형식 검사에 걸린다
PetBirthDate = Annotated[
    str | None,
    BeforeValidator(lambda v: v or None),
    AfterValidator(lambda v: v if v is None else _check_birth_date(v)),
]


class RecommendRequest(BaseModel):
    """routes/recommend 요청 바디. profile.build_profile()의 raw 인자 + candidates()/recommend()가 쓰는 값."""

    user_query: str
    animal_category: str | None = None
    size_category: str | None = None
    allergy: str | None = None
    n_pick: int = 5


class AskRequest(BaseModel):
    """routes/ask 요청 바디. pet_id 를 주면 그 펫의 DB 프로필을 그대로 쓴다(관리자 대시보드용).
    user_id 를 주면 그 고객의 실제 구매 이력을 [고객 정보]로 함께 넘긴다 - 없으면 검색 후보와
    실제 구매가 섞여서 '이 고객' 질문에 LLM이 근거 없이 답할 수 있다."""

    user_query: str
    pet_id: int | None = None
    user_id: int | None = None
    animal_category: str | None = None
    size_category: str | None = None
    allergy: str | None = None


class AskMeRequest(BaseModel):
    """routes/ask 의 /ask/me 요청 바디 - 일반 회원용. user_id/pet_id를 안 받는다 -
    토큰(get_current_user)에서만 가져와야 다른 회원 구매 이력을 못 들여다본다."""

    user_query: str


class Pick(BaseModel):
    product_id: int
    reason: str


class RecommendResponse(BaseModel):
    """recommend()의 (picks, retries, last_error) 튜플을 그대로 담는다."""

    picks: list[Pick]
    retries: int
    error: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminLoginRequest(BaseModel):
    """관리자 로그인 - 계정 없이 공용 비밀번호만 받는다."""

    password: str


class SignupRequest(BaseModel):
    """일반 회원가입 - 계정 정보 + 반려동물(강아지) 프로필 + 설문(알러지/식성/피부/활동량)을 한 번에 받는다.
    gender는 pet 테이블 CHECK 제약과 같은 값('M'/'F')만 받는다.
    pet_allergies는 GET /allergens가 준 이름(name_ko) 그대로 - id는 서버가 CommonMgr로 알아서 바꾼다."""

    email: str
    password: str
    name: str
    phone: str | None = None
    region: str | None = None
    pet_name: str
    pet_species: str | None = None
    pet_gender: str | None = None
    pet_birth_date: PetBirthDate = None
    pet_weight_kg: float | None = Field(default=None, gt=0, le=150)
    pet_size: int | None = None
    pet_activity_level: int | None = None
    pet_allergies: list[str] | None = None
    diet_note: str | None = None
    skin_note: str | None = None


class CustomerUpdate(BaseModel):
    """관리자 회원 수정 요청 바디. 준 필드만 바꾼다 — 전부 선택값.
    pet_* · 설문 칸은 pet_id 로 고른 펫 것이다. 값 범위는 pet 테이블 CHECK 제약과 같다."""

    name: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=1)
    phone: str | None = None
    region: str | None = None
    pet_id: int | None = None
    pet_name: str | None = Field(default=None, min_length=1)
    pet_gender: Literal["M", "F"] | None = None
    pet_birth_date: PetBirthDate = None
    pet_weight_kg: float | None = Field(default=None, gt=0, le=150)
    pet_size: int | None = Field(default=None, ge=1, le=5)
    pet_neutered: int | None = Field(default=None, ge=0, le=1)
    pet_activity_level: int | None = Field(default=None, ge=1, le=3)
    pet_allergies: list[str] | None = None
    diet_note: str | None = None
    skin_note: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ReviewRequest(BaseModel):
    """POST /me/purchases/{id}/review 요청 바디. review 테이블 CHECK 제약과 같은 범위만 받는다."""

    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=1)


class BuyRequest(BaseModel):
    """POST /me/purchases 요청 바디 - 추천 카드의 '구매하기'가 보낸다."""

    product_id: int
    quantity: int = Field(default=1, ge=1)


class ProductCreate(BaseModel):
    """상품 등록 요청 바디. product 테이블 컬럼 중 서버가 채우는 값(product_id, created_at, updated_at)만 뺐다."""

    product_category_id: int
    brand: str
    name: str
    food_form: str | None = None
    price_krw: int
    weight_g: int
    kcal_per_100g: int | None = None
    target_size_min: int = 1
    target_size_max: int = 5
    target_age_min_month: int = 0
    target_age_max_month: int = 1200
    description: str | None = None
    ingredients_verified: int = 0
    is_active: int = 1


class ProductUpdate(BaseModel):
    """상품 수정 요청 바디. 준 필드만 바꾼다 — 전부 선택값."""

    product_category_id: int | None = None
    brand: str | None = None
    name: str | None = None
    food_form: str | None = None
    price_krw: int | None = None
    weight_g: int | None = None
    kcal_per_100g: int | None = None
    target_size_min: int | None = None
    target_size_max: int | None = None
    target_age_min_month: int | None = None
    target_age_max_month: int | None = None
    description: str | None = None
    ingredients_verified: int | None = None
    is_active: int | None = None


class Product(ProductCreate):
    """상품 조회 응답 바디. product 테이블 컬럼 전부."""

    product_id: int
    created_at: str
    updated_at: str
