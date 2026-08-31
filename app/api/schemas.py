# Last Updated : 2026-08-31

"""

API 요청/응답 형태를 정의하는 자리. 라우트 함수는 이 모델로 입출력을 검증한다.
들어오는 값들이 각 클래스별 클래스 변수들이 맞는지 봄.

브라우저(JS) → POST /search 요청 보냄 → FastAPI 서버가 처리 → 
SearchResponse 모양으로 응답 만듦 → 그 응답이 다시 브라우저로 돌아감 → 
JS가 그거 받아서 화면에 검색결과 뿌림

"""

from pydantic import BaseModel


# CHOI 추가. 사용자가 검색창에 자연어 질문 치고 "검색" 누르면 그 값이 들어오는 자리임.
class SearchRequest(BaseModel): 
    query: str
    animal_category: str | None = None  # 종 (개/고양이)
    size_category: str | None = None    # 체급 (초소형~초대형)
    allergy: str | None = None          # 알레르기 자유 텍스트
    top_k: int = 3



class SearchHit(BaseModel):
    purchase_id: str
    score: float
    text: str

class SearchResponse(BaseModel):
    hits: list[SearchHit]


class GoogleLoginRequest(BaseModel):
    id_token: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
