# Last Updated : 2026-09-04

"""관리자 대시보드 '질문' 탭. logs/query_log.jsonl에 쌓인 customer_question 줄을 그대로 보여준다."""

from fastapi import APIRouter, Depends

from app.core.auth import get_current_admin
from app.core.trace import read_customer_questions

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/api/questions")
def list_questions(limit: int = 50) -> list[dict]:
    """최근 고객 질문부터 최대 limit개."""
    return read_customer_questions(limit)
