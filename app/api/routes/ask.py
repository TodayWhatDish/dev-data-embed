"""사용자 질문에 답하는 스트리밍 엔드포인트. 흐름 조립은 services/answering.ask_stream()이 한다.

- /ask     : 관리자 대시보드가 고객을 골라 그 고객 대신 질문한다. pet_id/user_id를
             요청 바디에서 그대로 받는다 - 호출자가 관리자라 신뢰할 수 있다.
- /ask/me  : 로그인한 일반 회원이 자기 자신에 대해 묻는다. user_id를 바디로 안 받고
             토큰(get_current_user)에서만 가져온다 - 바디로 받으면 user_id만 바꿔서
             다른 회원 구매 이력을 조회하는 경로가 생긴다.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_admin, get_current_user
from app.api.schemas import AskMeRequest, AskRequest
from app.services.answering import ask_stream
from app.services.profile import primary_pet

router = APIRouter()


@router.post("/ask", dependencies=[Depends(get_current_admin)])
def ask(body: AskRequest):
    """관리자 대시보드용. pet_id 가 오면 그 펫의 DB 프로필을 쓰고, 없으면 요청에 직접 적힌 필터를 쓴다."""
    lines = ask_stream(body.user_query, body.pet_id, body.user_id, body.model_dump())
    return StreamingResponse(lines, media_type="application/x-ndjson")


@router.post("/ask/me")
def ask_me(body: AskMeRequest, user_id: int = Depends(get_current_user)):
    """일반 회원용. 로그인한 본인의 첫 번째 펫 프로필로 묻는다."""
    pet = primary_pet(user_id)
    lines = ask_stream(body.user_query, pet["pet_id"] if pet else None, user_id)
    return StreamingResponse(lines, media_type="application/x-ndjson")
