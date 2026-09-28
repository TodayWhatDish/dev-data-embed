# Last Updated : 2026-09-27

"""/ask/me 로 들어온 고객 질문 기록과 조회. 관리자 대시보드 '질문' 탭이 읽는다."""

import logging

from sqlalchemy.orm import Session

from app.repositories import questions as question_repo

logger = logging.getLogger()


def log_customer_question(
    db: Session,
    *,
    user_id: int | None,
    pet_id: int | None,
    user_query: str,
    matches: list[dict],
    answer: str,
    ok: bool,
    error: str | None = None,
) -> None:
    """고객 질문 한 건을 customer_question 에 남긴다 (관리자 /ask 는 graph/nodes._log 가 거른다).

    기록 실패가 답변을 끊으면 안 되므로 예외는 로그만 남기고 삼킨다.
    """
    matched = [
        {"product_id": m["product_id"], "name": m["name"], "product_type": m.get("product_type"), "score": m["score"]}
        for m in matches
    ]
    try:
        question_repo.create_question(db, user_id, pet_id, user_query, matched, answer, ok, error)
    except Exception:
        logger.exception(f"질문 기록 실패: user_id={user_id}, query={user_query!r}")


def list_questions(db: Session, limit: int) -> list[dict]:
    """최근 고객 질문부터 최대 limit개."""
    return question_repo.list_recent(db, limit)
