# Last updated: 2026-09-03

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
     "너는 반려동물 사료 상담 담당자다. [고객 정보]는 이 고객이 실제로 구매한 이력이고, "
     "[추천 후보]는 조건에 맞춰 검색된 상품/리뷰로 다른 고객이 쓴 것도 섞여 있다 - 이 고객의 구매가 아니다. "
     "이 고객에 대한 질문(구매 여부·횟수 등)은 반드시 [고객 정보]만 근거로 답하고, [추천 후보]를 근거로 쓰지 않는다. "
     "두 정보 모두에 없으면 '자료에 없다'고 말한다. 지어내지 않는다. 3~5문장으로 짧게 쓴다."),
    ("human", "[고객 정보]\n{customer_context}\n\n[추천 후보]\n{context}\n\n[질문]\n{question}"),
])

def build_customer_context(detail: dict[str, Any] | None) -> str:
    """이 고객의 실제 구매 이력을 사실 그대로 요약한다.

    candidates()가 찾은 검색 후보(다른 고객 리뷰 포함 가능)와 절대 섞이면 안 되므로
    프롬프트에서 별도 슬롯([고객 정보])으로 분리해 넘긴다.
    """
    if not detail or not detail["purchases"]:
        return "구매 이력 없음"
    lines = [
        f"-{p['product_name']} | 평점: {p.get('rating')} | 리뷰: {p.get('review_body') or '(리뷰 없음)'}"
        for p in detail["purchases"]
    ]
    return f"총 {len(detail['purchases'])}건 구매\n" + "\n".join(lines)

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

class Citation(BaseModel):
    purchase_id: int = Field(description="근거로 삼은 purchase_id. 반드시 자료 목록에 있는 값만 쓴다")
    quote: str = Field(description="그 구매/리뷰에서 근거로 삼은 내용 요약, 한 문장")

class Strategy(BaseModel):
    strategy: str = Field(description="이 고객 대상 판매전략·마케팅·CS 응대 방향, 3~5문장")
    citations: list[Citation]

def build_strategy_prompt(detail: dict[str, Any]) -> str:
    """구매이력+리뷰를 근거자료로 묶어 전략 생성 프롬프트를 조립한다.
    citation을 후보 밖 purchase_id로 지어내지 못하게 실제 구매 목록을 전부 나열해서 넘긴다."""
    lines = [
        f"-purchase_id = {p['purchase_id']} | {p['product_name']} | 평점: {p.get('rating')} | 리뷰: {p.get('review_body') or '(리뷰 없음)'}"
        for p in detail["purchases"]
    ]
    return (
        f"고객: {detail['name']} ({detail.get('region') or ''})\n"
        f"아래는 이 고객의 구매이력이다. 이것만 근거로 판매전략과 CS 응대 방향을 제안하라.\n"
        f"citations의 purchase_id는 반드시 아래 목록에 있는 값만 써라. 없는 값을 지어내지 마라.\n\n"
        + "\n".join(lines)
    )

class FactCheck(BaseModel):
    accuracy: float = Field(description="0~1 사이 숫자. 답변이 [고객 정보]의 사실과 일치하는 정도")
    note: str = Field(description="이 점수를 매긴 근거. 답변의 어느 부분이 [고객 정보]의 어느 내용과 일치/불일치하는지 구체적으로 짚어서 설명한다")

def build_factcheck_prompt(customer_context: str, answer: str) -> str:
    """답변을 만든 모델과 별도 호출로 [고객 정보]와 대조한다 - 문자열 대조가 못 잡는 '재구매/평점 같은
    과거 사실 주장'이 의심될 때만 answering._looks_suspicious()가 이 프롬프트를 태운다."""
    return (
        f"[고객 정보]\n{customer_context}\n\n"
        f"[답변]\n{answer}\n\n"
        f"위 [답변]이 [고객 정보]의 사실과 일치하는지 확인하라. "
        f"[고객 정보]에 없는 내용을 답변이 사실처럼 말했다면 accuracy를 낮춰라. "
        f"note에는 채점 근거를 구체적으로 적어라."
    )

def build_answer_context(candidates: list[dict[str, Any]]) -> str:
    """searching.candidates()가 찾아준 후보 리뷰들을 답변용 '자료' 텍스트로 묶는다."""
    lines = [
        f"-product_id = {c['product_id']} | {c['name']} | {c['price_krw']}원 | 리뷰: {c['review']}"
        for c in candidates
    ]
    return "\n".join(lines)
