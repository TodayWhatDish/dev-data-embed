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

class Pick(BaseModel):
    product_id: int
    reason: str

class RecommendResponse(BaseModel):
    """recommend()의 (picks, retries, last_error) 튜플을 그대로 담는다."""
    picks: list[Pick]
    retries: int
    error: str

class GoogleLoginRequest(BaseModel):
    id_token: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
