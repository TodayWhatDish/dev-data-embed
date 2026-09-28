# Last Updated : 2026-09-27

"""/ask, /ask/me 로 들어온 질문 기록. 관리자 대시보드 '질문' 탭이 읽는다."""

import logging

from app.core.db import new_session
from app.repositories import questions as question_repo

logger = logging.getLogger()


def log_customer_question(
    *,
    user_id: int | None,
    pet_id: int | None,
    user_query: str,
    matches: list[dict],
    answer: str,
    ok: bool,
    error: str | None = None,
) -> None:
    """질문 한 건을 customer_question 에 남긴다.

    스트리밍 도중(generate() 안)에 불리므로 요청 세션이 이미 닫혀 있다 - 여기서 짧게 새로 연다.
    기록 실패가 답변을 끊으면 안 되므로 예외는 로그만 남기고 삼킨다.
    """
    matched = [
        {"product_id": m["product_id"], "name": m["name"], "product_type": m.get("product_type"), "score": m["score"]}
        for m in matches
    ]
    try:
        with new_session() as db:
            question_repo.create_question(db, user_id, pet_id, user_query, matched, answer, ok, error)
    except Exception:
        logger.exception(f"질문 기록 실패: user_id={user_id}, query={user_query!r}")
