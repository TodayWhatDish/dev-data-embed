# Last Updated : 2026-08-30

"""요청·응답의 모양을 한 곳에 모은다.

    라우트 함수가 dict 를 그대로 주고받으면 계약이 코드 안에만 남는다. 여기 두면
    /docs 가 그대로 문서가 되고, 잘못된 요청은 라우트에 닿기 전에 422 로 끊긴다.
"""
from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    """1번 '사용자 요청'의 모양.

    프로필 세 값은 전부 선택이다. retrieve.build_where 가 '값이 들어온 키만'
    WHERE 에 붙이므로, 빈 값은 조건을 거는 대신 그냥 넓게 검색하는 쪽이 맞다.
    """
    question: str = Field(min_length=1, description="사용자 질문")
    animal_category: str | None = Field(default=None, description="축종 (개/고양이)")
    size_category: str | None = Field(default=None, description="체구 (초소형~초대형)")
    allergy: str | None = Field(default=None, description="알레르겐 이름 (예: 닭고기)")
    top_k: int = Field(default=5, ge=1, le=20, description="검색해올 리뷰 수")
    n_pick: int = Field(default=3, ge=1, le=10, description="추천할 상품 수")


class Evidence(BaseModel):
    """추천 한 건이 인용한 후기."""
    id: str
    rating: int
    body: str


class Pick(BaseModel):
    """LLM 이 고른 상품 한 건. product_id 는 후보에 있던 값임이 검증된 뒤에만 실린다."""
    product_id: str
    name: str
    brand: str
    price_krw: int | None = None
    reason: str
    evidence: list[Evidence] = []


class RecommendResponse(BaseModel):
    """5번의 결과.

    retries 를 응답에 남긴다. 모델이 형식을 몇 번 만에 맞췄는지가 모델·프롬프트를
    바꿀 때 비교할 수 있는 유일한 자동 지표다. 로그만 남기면 나중에 못 센다.
    """
    answer: str
    picks: list[Pick]
    retries: int = 0
    searched: int = Field(default=0, description="검색된 리뷰 수")
