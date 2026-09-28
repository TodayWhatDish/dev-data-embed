# Last updated: 2026-09-28

"""searching.py가 넘겨준 후보를 LLM에게 보여줄 프롬프트로 조립하고, LLM 응답이 반드시 이 모양으로만 나오도록 강제하는 스키마를 정의한다.
프롬프트 조립과 응답 스키마는 한 쌍이라 이곳에 둔다.
"""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.domain.masking import mask


class Pick(BaseModel):
    product_id: int = Field(description="후보 목록에 있는 product_id 중 하나")
    reason: str = Field(description="이 상품을 고른 이유, 한두 문장")


class Recommendation(BaseModel):
    picks: list[Pick]


ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "너는 반려동물 사료 상담 담당자다. [고객 정보]는 이 고객이 실제로 구매한 이력이고, "
            "[추천 후보]는 조건에 맞춰 검색된 상품/리뷰로 다른 고객이 쓴 것도 섞여 있다 - 이 고객의 구매가 아니다. "
            "이 고객의 과거 사실(구매 여부·횟수·추이 등)은 반드시 [고객 정보]만 근거로 답하고, [추천 후보]를 근거로 쓰지 않는다. "
            "상품 추천 요청은 [추천 후보]에서 골라 답한다. 상품명·가격·후기는 [추천 후보]에 있는 것만 쓴다. "
            "산책·목욕·행동·건강 같은 일반 반려동물 질문은 일반 상식으로 답하되 '일반적인 정보'임을 밝히고, "
            "질병이 의심되는 증상이면 동물병원 진료를 권한다. 관련 있으면 [추천 후보]에서 하나를 곁들인다. "
            "반려동물과 무관한 질문은 한 문장으로 사료·간식 상담만 돕는다고 안내한다. "
            "이 고객의 사실이나 상품 정보가 필요한데 근거가 없으면 '가진 자료로는 확인할 수 없어요'라고 말한다. "
            "지어내지 않는다. 존댓말로 3~5문장 짧게 쓴다. "
            "답변에서 고객을 부를 땐 이름 대신 '고객님'이라고 쓴다. "
            "[성분표]는 후보 상품의 등록 성분(%)이다 - 성분·영양 수치는 [성분표]에 있는 값만 쓴다.",
        ),
        (
            "human",
            "[고객 정보]\n{customer_context}\n\n[추천 후보]\n{context}\n\n[성분표]\n{nutrition_context}\n\n[질문]\n{question}",
        ),
    ]
)


class Plan(BaseModel):
    nutrition: bool = Field(
        description="질문이 성분·영양 수치(단백질·지방·섬유·칼슘·인·나트륨·수분 등)를 묻거나 비교할 때만 true. "
        "알러지·체급·기호에 맞는 일반 추천은 false"
    )


def build_plan_prompt(question: str) -> str:
    """질문만 보고 어떤 도구가 필요한지 고르게 한다. 후보·고객 정보는 안 넘긴다 - retrieve 와 동시에 돈다."""
    return (
        "반려동물 사료 상담 질문이다. 기본은 도구 없이 리뷰 검색만으로 답한다.\n"
        "성분표는 질문에 성분명(단백질·지방·섬유·회분·수분·칼슘·인·나트륨)이나 함량·퍼센트가 나올 때만 쓴다.\n"
        "예) '단백질 높은 사료', '나트륨 적은 거' -> nutrition=true / "
        "'알러지 있는 강아지 사료 추천', '입 짧은 노견 간식', '또 사도 될까' -> nutrition=false\n\n"
        f"[질문]\n{question}"
    )


NUTRITION_LABELS = {
    "crude_protein_pct": "조단백",
    "crude_fat_pct": "조지방",
    "crude_fiber_pct": "조섬유",
    "crude_ash_pct": "조회분",
    "moisture_pct": "수분",
    "calcium_pct": "칼슘",
    "phosphorus_pct": "인",
    "sodium_pct": "나트륨",
}


def build_nutrition_context(candidates: list[dict[str, Any]], nutritions: dict[int, dict] | None) -> str:
    """후보 상품의 성분표를 한 줄씩. 조회 안 했으면(None) 그렇다고, 조회했는데 없으면 없다고 적는다."""
    if nutritions is None:
        return "조회하지 않음"
    names = {c["product_id"]: c["name"] for c in candidates}
    lines = [
        f"-product_id = {pid} | {names.get(pid, '')} | "
        + ", ".join(f"{label} {row[key]}%" for key, label in NUTRITION_LABELS.items() if row.get(key) is not None)
        for pid, row in nutritions.items()
    ]
    return "\n".join(lines) or "후보 상품의 성분 정보 없음"


def build_customer_context(detail: dict[str, Any] | None) -> str:
    """이 고객의 실제 구매 이력을 사실 그대로 요약한다.

    candidates()가 찾은 검색 후보(다른 고객 리뷰 포함 가능)와 절대 섞이면 안 되므로
    프롬프트에서 별도 슬롯([고객 정보])으로 분리해 넘긴다.
    """
    if not detail:
        return "구매 이력 없음"
    # 이름이 있어야 '강나연씨의 ~' 처럼 이름으로 물어도 같은 고객으로 알아본다
    header = f"고객: {detail['name']}"
    purchases = detail["purchases"]
    if not purchases:
        return f"{header}\n구매 이력 없음"
    # 구매일·금액이 있어야 '구매 추이' 같은 시간 질문에 답할 수 있다
    lines = [_format_purchase(p) for p in purchases]
    return f"{header}\n총 {len(purchases)}건 구매 (최신순)\n" + "\n".join(lines)


def _format_purchase(purchase: dict[str, Any]) -> str:
    """구매 한 건을 '날짜 | 상품 | 금액 | 평점 | 리뷰' 한 줄로."""
    purchased_on = str(purchase.get("purchased_at") or "")[:10]
    amount = (purchase.get("unit_price_krw") or 0) * (purchase.get("quantity") or 1)
    review = mask(purchase.get("review_body")) or "(리뷰 없음)"
    return f"-{purchased_on} | {purchase['product_name']} | {amount:,}원 | 평점: {purchase.get('rating')} | 리뷰: {review}"


def build_recommend_prompt(candidate: list[dict[str, Any]], profile: dict[str, Any], n_pick: int) -> str:
    """LLM이 후보 중에서만 n_pick개를 고르도록 프롬프트를 조립한다.
    후보 밖 product_id를 지어내지 못하게 후보를 전부 나열해서 넘긴다."""
    lines = [
        f"-product_id = {c['product_id']} | {c['name']} | {c['price_krw']}원 | 리뷰: {mask(c['review'])}"
        for c in candidate
    ]
    return (
        f"사용자 프로필: {profile}\n"
        f"아래 후보 중에서만 정확히 {n_pick}개를 고르고, 각각 고른 이유를 적어라.\n"
        f"후보 목록에 없는 product_id는 절대 쓰지 마라.\n\n" + "\n".join(lines)
    )


class Citation(BaseModel):
    purchase_id: int = Field(description="근거로 삼은 purchase_id. 반드시 자료 목록에 있는 값만 쓴다")
    quote: str = Field(description="그 구매/리뷰에서 근거로 삼은 내용 요약, 한 문장")


class Strategy(BaseModel):
    # 문자열 한 칸이라 모델이 "다음과 같은 전략을 제안합니다." 같은 서론만 쓰고 닫아 버리는 일이 있다 - 본문을 이 칸에 직접 쓰게 한다
    strategy: str = Field(
        description="이 고객 대상 판매전략·마케팅·CS 응대 방향, 3~5문장. 서론 없이 구체적인 전략 내용 자체를 쓴다 - "
        "'다음과 같은 전략을 제안합니다'처럼 뒤에 내용이 이어질 것처럼 끝내지 않는다"
    )
    citations: list[Citation]


def build_strategy_prompt(detail: dict[str, Any]) -> str:
    """구매이력+리뷰를 근거자료로 묶어 전략 생성 프롬프트를 조립한다.
    citation을 후보 밖 purchase_id로 지어내지 못하게 실제 구매 목록을 전부 나열해서 넘긴다."""
    lines = [
        f"-purchase_id = {p['purchase_id']} | {p['product_name']} | 평점: {p.get('rating')} | 리뷰: {mask(p.get('review_body')) or '(리뷰 없음)'}"
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
    note: str = Field(
        description="이 점수를 매긴 근거. 답변의 어느 부분이 [고객 정보]의 어느 내용과 일치/불일치하는지 구체적으로 짚어서 설명한다"
    )


def build_factcheck_prompt(customer_context: str, answer: str) -> str:
    """답변을 만든 모델과 별도 호출로 [고객 정보]와 대조한다 - 문자열 대조가 못 잡는 '재구매/평점 같은
    과거 사실 주장'이 의심될 때만 answering._looks_suspicious()가 이 프롬프트를 태운다."""
    return (
        f"[고객 정보]\n{customer_context}\n\n"
        f"[답변]\n{answer}\n\n"
        f"위 [답변]이 [고객 정보]의 사실과 일치하는지 확인하라. "
        f"[고객 정보]에 없는 이 고객의 사실(구매·펫 정보 등)을 답변이 사실처럼 말했다면 accuracy를 낮춰라. "
        f"일반 반려동물 상식이나 상품 추천은 고객 사실이 아니므로 감점하지 않는다. "
        f"note에는 채점 근거를 구체적으로 적어라."
    )


def build_answer_context(candidates: list[dict[str, Any]]) -> str:
    """searching.candidates()가 찾아준 후보 리뷰들을 답변용 '자료' 텍스트로 묶는다."""
    lines = [
        f"-product_id = {c['product_id']} | {c['name']} | {c['price_krw']}원 | 리뷰: {mask(c['review'])}"
        for c in candidates
    ]
    return "\n".join(lines)
