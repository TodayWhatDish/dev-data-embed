# Last Updated : 2026-09-27

"""/ask/me 로 들어온 고객 질문 기록과 조회. 관리자 대시보드 '질문' 탭이 읽는다."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import ASK_DAILY_MAX
from app.repositories import questions as question_repo

logger = logging.getLogger()

# 한국은 서머타임이 없어 고정 +9 로 충분하다 (zoneinfo 는 Windows 에서 tzdata 가 따로 필요하다)
KST = timezone(timedelta(hours=9))


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


def questions_left_today(db: Session, user_id: int) -> int:
    """오늘(한국 시간) 남은 질문 수. created_at 이 UTC 문자열이라 한국 자정을 UTC 로 바꿔 비교한다.
    ponytail: 기록이 답변 끝에 남아서 동시에 여러 개를 보내면 한도를 조금 넘을 수 있다 - ask_limit(분당)가 상한."""
    kst_midnight = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    since = kst_midnight.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return max(ASK_DAILY_MAX - question_repo.count_since(db, user_id, since), 0)


def list_questions(db: Session, limit: int) -> list[dict]:
    """최근 고객 질문부터 최대 limit개."""
    return question_repo.list_recent(db, limit)
