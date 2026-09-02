# Last updated: 2026-09-01

""" candidates()가 찾아준 후보 리뷰를 근거로, 자유 텍스트 답변을 조각조각 스트리밍하는 자리.
    구조화 출력(추천)과 달리 여기는 형식 검증이 없다 - 자유 문장이라 검증할 스키마가 없기 때문이다.
"""
from typing import Any, Iterator

from langchain_core.output_parsers import StrOutputParser

from app.adapters.stores.llm import chat, chat_answer
from app.domain.prompting import ANSWER_PROMPT, FactCheck, build_answer_context, build_factcheck_prompt

ANSWER_CHAIN = ANSWER_PROMPT | chat_answer | StrOutputParser()


def stream(user_query: str, candidates: list[dict[str, Any]], customer_context: str = "정보 없음") -> Iterator[str]:
    """검색 후보와 실제 고객 구매 이력을 분리된 슬롯으로 넘기고, 모델이 흘려보내는 글자 조각을 그대로 다시 흘려보낸다."""
    context = build_answer_context(candidates)
    yield from ANSWER_CHAIN.stream({"context": context, "customer_context": customer_context, "question": user_query})


def verify(customer_context: str, answer: str) -> dict[str, Any]:
    """다 나온 답변을, 답변을 만든 모델과 별도 호출로 실제 구매 이력과 대조해 정확도를 매긴다."""
    prompt = build_factcheck_prompt(customer_context, answer)
    result: FactCheck = chat.with_structured_output(FactCheck).invoke(prompt)
    return result.model_dump()
