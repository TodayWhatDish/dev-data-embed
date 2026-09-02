# Last Updated : 2026-08-31

""" API 요청/응답 형태를 정의하는 자리. 라우트 함수는 이 모델로 입출력을 검증한다.
    들어오는 값들이 각 클래스별 클래스 변수들이 맞는지 봄.

    브라우저(JS) → POST /search 요청 보냄 → FastAPI 서버가 처리 → 
    SearchResponse 모양으로 응답 만듦 → 그 응답이 다시 브라우저로 돌아감 → 
    JS가 그거 받아서 화면에 검색결과 뿌림
"""

from pydantic import BaseModel

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


