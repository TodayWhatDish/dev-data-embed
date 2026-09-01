# Last updated: 2026-09-01

""" searching.py가 넘겨준 후보를 LLM에게 보여줄 프롬프트로 조립하고, LLM 응답이 반드시 이 모양으로만 나오도록 강제하는 스키마를 정의한다.
    프롬프트 조립과 응답 스키마는 한 쌍이라 이곳에 둔다. 
"""
from typing import Any
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
class Pick(BaseModel):
    product_id: int = Field(description="후보 목록에 있는 product_id 중 하나")
    reason: str = Field(description="이 상품을 고른 이유, 한두 문장")

class Recommendation(BaseModel):
    picks: list[Pick]


ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "너는 반려동물 사료 상담 담당자다. 주어진 '자료' 안에 있는 내용만 근거로 한국어로 답한다. "
     "자료에 없으면 '자료에 없다'고 말한다. 지어내지 않는다. 3~5문장으로 짧게 쓴다."),
    ("human", "{context}\n\n[질문]\n{question}"),
])

def build_recommend_prompt(candidate: list[dict[str,Any]], profile: dict[str, Any], n_pick: int) -> str:
    """LLM이 후보 중에서만 n_pick개를 고르도록 프롬프트를 조립한다.
    후보 밖 product_id를 지어내지 못하게 후보를 전부 나열해서 넘긴다."""
    lines = [
        f"-product_id = {c['product_id']} | {c['name']} | {c['price_krw']}원 | 리뷰: {c['review']}"
        for c in candidate
    ]
    return (
        f"사용자 프로필: {profile}\n"
        f"아래 후보 중에서만 정확히 {n_pick}개를 고르고, 각각 고른 이유를 적어라.\n"
        f"후보 목록에 없는 product_id는 절대 쓰지 마라.\n\n"
        + "\n".join(lines)
    )

def build_answer_context(candidates: list[dict[str, Any]]) -> str:
    """searching.candidates()가 찾아준 후보 리뷰들을 답변용 '자료' 텍스트로 묶는다."""
    lines = [
        f"-product_id = {c['product_id']} | {c['name']} | {c['price_krw']}원 | 리뷰: {c['review']}"
        for c in candidates
    ]
    return "\n".join(lines)
