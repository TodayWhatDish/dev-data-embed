# Last updated: 2026-09-03

""" candidates()가 찾아준 후보 리뷰를 근거로, 자유 텍스트 답변을 조각조각 스트리밍하는 자리.
    구조화 출력(추천)과 달리 여기는 형식 검증이 없다 - 자유 문장이라 검증할 스키마가 없기 때문이다.
"""
from typing import Any, Iterator

from langchain_core.output_parsers import StrOutputParser

from app.adapters.stores.llm import chat_answer, chat_verify
from app.domain.prompting import ANSWER_PROMPT, FactCheck, build_answer_context, build_customer_context, build_factcheck_prompt

ANSWER_CHAIN = ANSWER_PROMPT | chat_answer | StrOutputParser()

def stream(user_query: str, candidates: list[dict[str, Any]], customer_context: str = "정보 없음") -> Iterator[str]:
    """검색 후보와 실제 고객 구매 이력을 분리된 슬롯으로 넘기고, 모델이 흘려보내는 글자 조각을 그대로 다시 흘려보낸다."""
    context = build_answer_context(candidates)
    yield from ANSWER_CHAIN.stream({"context": context, "customer_context": customer_context, "question": user_query})


def verify(detail: dict[str, Any] | None, answer: str) -> dict[str, Any]:
    """1차: 문자열 대조(공짜, 즉시) - 펫 이름이 답변에 등장하는지만 본다.
    2차: 대조할 실제 고객 정보(detail)가 있으면, 질문이 뭐든 상관없이 항상 LLM 채점도 돌린다.

    ponytail: "의심될 때만 LLM"으로 키워드 트리거를 쓰다가 뺐다 - 질문 종류가 늘어날 때마다
    키워드를 계속 추가해야 해서 범용 질문을 못 커버한다. 판단 대상이 범용적(자유 질문)이면
    판단 주체도 범용적(LLM)이어야 한다 - 대신 대조할 정보가 없는 요청(user_id 없음)은 건너뛴다.
    상품명 grounding은 뺐다 - [추천 후보](안 산 상품)를 언급하는 게 정상 동작이라
    문자열만 보고는 정상 추천/오답을 못 가른다.
    """
    known_pets = {p["name"] for p in (detail["pets"] if detail else [])}
    mentioned_pets = [name for name in known_pets if name in answer]
    accuracy = len(mentioned_pets) / len(known_pets) if known_pets else 1.0
    result: dict[str, Any] = {
        "accuracy": accuracy,
        "note": f"실제 펫 이름 언급: {', '.join(mentioned_pets)}" if mentioned_pets else "답변에서 이 고객의 펫 이름이 확인되지 않음",
        "grounded_pets": mentioned_pets,
        "llm_checked": False,
    }

    if detail:
        customer_context = build_customer_context(detail)
        prompt = build_factcheck_prompt(customer_context, answer)
        verifier = chat_verify.with_structured_output(FactCheck).with_retry(stop_after_attempt=3)
        judged: FactCheck = verifier.invoke(prompt)
        result.update(judged.model_dump())
        result["llm_checked"] = True

    return result
