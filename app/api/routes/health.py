# Last Updated : 2026-08-30

"""서버가 살아있는지 확인하는 Health Check. 배포 환경에서 로드밸런서가 주기적으로 호출한다."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
