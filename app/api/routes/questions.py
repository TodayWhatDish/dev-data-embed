# Last Updated : 2026-09-27

"""관리자 대시보드 '질문' 탭. customer_question 테이블의 최근 질문을 보여준다."""

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_admin
from app.services import questions

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/api/questions")
def list_questions(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    """최근 고객 질문부터 최대 limit개."""
    return questions.list_questions(limit)
