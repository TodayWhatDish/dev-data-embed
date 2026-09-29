"""ask 그래프를 흐르는 값. 노드는 바꾼 키만 dict 로 반환한다."""

from typing import TypedDict


class AskState(TypedDict, total=False):
    question: str
    pet_id: int | None
    user_id: int | None
    profile_filters: dict | None
    log_question: bool        # False면 '질문' 탭 기록을 남기지 않는다 (관리자 /ask)

    tools: list[str]          # plan 이 채움: 부를 도구 이름들 (예: ["nutrition"])
    matches: list[dict]       # retrieve 가 채움: 검색된 후보 리뷰
    detail: dict | None       # retrieve 가 채움: 반증에 쓸 고객 정보
    customer_context: str     # retrieve 가 채움: 프롬프트에 넣을 고객 정보 문장
    nutritions: dict[int, dict] | None  # run_tools 가 채움: 후보 상품 성분표. 안 불렀으면 None
    answer: str               # generate 가 채움
    failed: bool              # generate 가 LLM 실패 시 True
