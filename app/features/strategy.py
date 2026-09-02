# Last updated: 2026-09-02

""" 구매이력을 근거로 판매전략/CS 응대안을 생성하고, LLM이 인용한 근거가 실제 이 고객의
    구매인지 SQL로 대조하는 자리 (DESIGN.md §7 요구사항 5, 6).

    알러지 판정(§3)과 같은 원칙 - LLM이 "이게 근거다"라고 말한 걸 그대로 믿지 않는다.
    없는 구매를 근거로 대는 환각은 재질문이 아니라 SQL 대조로만 확실히 잡힌다.
"""
from typing import Any

from app.adapters.stores.llm import chat
from app.domain.prompting import Strategy, build_strategy_prompt
from app.repositories import users as users_repo


def generate_strategy(user_id: int) -> dict[str, Any] | None:
    """구매 이력이 없으면 None. 있으면 전략 텍스트 + 인용별 verified 플래그를 담아 돌려준다."""
    detail = users_repo.get_user_detail(user_id)
    if detail is None or not detail["purchases"]:
        return None

    prompt = build_strategy_prompt(detail)
    result: Strategy = chat.with_structured_output(Strategy).invoke(prompt)

    owned = {p["purchase_id"] for p in detail["purchases"]}
    citations = [
        {**c.model_dump(), "verified": c.purchase_id in owned}
        for c in result.citations
    ]
    return {"strategy": result.strategy, "citations": citations}
