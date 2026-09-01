# Last updated: 2026-08-31

""" searching.py가 좁혀준 후보 안에서만 LLM이 고르도록 강제하고, 형식 깨진 응답을 재시도로 잡는 자리.
    이 검증이 없으면 LLM이 후보에 없는 상품을 지어내도 그대로 나감.
"""
from typing import Any
from app.domain.prompting import Recommendation,build_recommend_prompt
from app.adapters.stores.llm import chat
MAX_RETRIES = 2

def recommend(candidates: list[dict[str,Any]], profile: dict[str,Any], n_pick: int = 5) -> tuple[Any, int, str]:
    """후보 중에 n_pick개 만큼 고른 결과와 재시도 횟수, 마지막 오류를 돌려준다."""
    valid_ids = {c["product_id"] for c in candidates}
    prompt = build_recommend_prompt(candidates,profile,n_pick)
    structured_chat = chat.with_structured_output(Recommendation)

    last_error = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            result: Recommendation = structured_chat.invoke(prompt)
        except Exception as exc:
            # 채우기: last_error에 str(exc) 담고, 이번 attempt는 결과가 없으니
            # 아래 검증 코드로 안 내려가고 바로 다음 attempt로 넘어가야 함 (continue)
            ...

        # 후보 밖 product_id가 섞였는지, 개수가 n_pick과 맞는지 검증한다.
        bad_ids = [p.product_id for p in result.picks if p.product_id not in valid_ids]
        if not bad_ids and len(result.picks) == n_pick:
            return [p.model_dump() for p in result.picks], attempt, ""
        last_error = f"잘못된 product_id: {bad_ids}" if bad_ids else f"개수 불일치: {len(result.picks)}개 (요청 {n_pick}개)"

    return [], MAX_RETRIES, last_error
    

