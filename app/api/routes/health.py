# Last Updated : 2026-09-02

""" 운영 상태 체크용 API으로 관리자 대시보드와 운영 모니터링이 서버가 실제로 준비됐는지 빠르게 확인할 수 있도록
    /health /ready 엔드포인트를 제공한다.
    /health : 서버가 살아있는지 확인하는 Health Check. 배포 환경에서 로드밸런서(load balancer)가 주기적으로 호출
    /ready : 서버가 실제로 요청을 처리할 준비가 됐는지 확인하는 Readiness Check. 배포 환경에서 로드밸런서가 주기적으로 호출
"""

from fastapi import APIRouter

from app.adapters.stores.llm import chat
from app.core.db import con
from app.core.config import LLM_API_KEY

router = APIRouter()

@router.get("/health")
def health() -> dict:
    """서버가 살아 있는지 확인하는 기본 health check"""
    return {"status":"ok"}

@router.get("/ready")
def ready() -> dict:
    """DB와 LLM이 실제로 준비됐는지 확인한다."""
    db_ok = False
    llm_ok = False

    try:
        con.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False

    llm_ok = bool(LLM_API_KEY)

    return {
        "db": db_ok,
        "llm": llm_ok,
        "ready": db_ok and llm_ok,
    }

