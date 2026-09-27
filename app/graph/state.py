"""ask 그래프를 흐르는 값. 노드는 바꾼 키만 dict 로 반환한다."""

from typing import TypedDict


class AskState(TypedDict, total=False):
    question: str
    pet_id: int | None
    user_id: int | None
    profile_filters: dict | None

    matches: list[dict]       # retrieve 가 채움: 검색된 후보 리뷰
    detail: dict | None       # retrieve 가 채움: 반증에 쓸 고객 정보
    customer_context: str     # retrieve 가 채움: 프롬프트에 넣을 고객 정보 문장
    answer: str               # generate 가 채움
    failed: bool              # generate 가 LLM 실패 시 True