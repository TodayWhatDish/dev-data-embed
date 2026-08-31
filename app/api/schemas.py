# Last Updated : 2026-08-31

""" routes/recommend 엔드포인트의 요청/응답 모양을 고정한다.
    라우터가 이 타입으로 FastAPI의 자동 검증 + response_model 문서화를 받는다.
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