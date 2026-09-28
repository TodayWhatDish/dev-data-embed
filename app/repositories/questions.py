# Last Updated : 2026-09-27

"""customer_question 테이블에 닿는 자리. 질문 한 건 저장 + 관리자 '질문' 탭 조회."""

from app.core.db import commit, get_session
from app.models.question import CustomerQuestion


def create_question(
    user_id: int | None,
    pet_id: int | None,
    user_query: str,
    matched: list[dict],
    answer: str,
    ok: bool,
    error: str | None,
) -> None:
    get_session().add(
        CustomerQuestion(
            user_id=user_id,
            pet_id=pet_id,
            user_query=user_query,
            matched=matched,
            answer=answer,
            ok=ok,
            error=error,
        )
    )
    commit("customer_question")


def list_recent(limit: int) -> list[dict]:
    """최근 질문부터 최대 limit개. 모양은 jsonl 시절 그대로(time 키) - 관리자 화면이 이 키를 읽는다."""
    rows = get_session().query(CustomerQuestion).order_by(CustomerQuestion.question_id.desc()).limit(limit).all()
    return [
        {
            "time": q.created_at,
            "user_id": q.user_id,
            "pet_id": q.pet_id,
            "user_query": q.user_query,
            "matched": q.matched,
            "answer": q.answer,
            "ok": q.ok,
            "error": q.error,
        }
        for q in rows
    ]
