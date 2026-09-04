# Last Updated : 2026-09-04

""" 사용자 질문에 답하는 스트리밍 엔드포인트. 두 자리에서 부른다.

    - /ask     : 관리자 대시보드가 고객을 골라 그 고객 대신 질문한다. pet_id/user_id를
                 요청 바디에서 그대로 받는다 - 호출자가 관리자라 신뢰할 수 있다.
    - /ask/me  : 로그인한 일반 회원이 자기 자신에 대해 묻는다. user_id를 바디로 안 받고
                 토큰(get_current_user)에서만 가져온다 - 바디로 받으면 user_id만 바꿔서
                 다른 회원 구매 이력을 조회하는 경로가 생긴다.

    - 질문을 받는다
    - 프로필과 후보를 구성한다
    - 답변을 스트리밍으로 전달한다
    - 데이터가 없으면 에러 메시지를 NDJSON으로 반환한다
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.schemas import AskMeRequest, AskRequest
from app.core.auth import get_current_admin, get_current_user
from app.domain.prompting import build_customer_context
from app.features import answering
from app.features.profile import build_profile, pet_profile
from app.features.searching import candidates
from app.repositories import users as users_repo
from app.repositories.pet import find_pets_by_user

router = APIRouter()


def _stream_answer(user_query: str, pet_id: int | None, user_id: int | None,
                    profile_filters: dict | None = None) -> StreamingResponse:
    """profile 구성 -> 후보 검색 -> 답변 스트리밍 순서로 엮는다. /ask, /ask/me 둘 다 여기로 모인다.

    pet_id 가 오면 그 펫의 DB 프로필을 쓴다. 없으면 profile_filters(요청에 직접 적힌 필터)를 쓴다.
    """
    profile = pet_profile(pet_id) if pet_id else build_profile(profile_filters or {})
    matches = candidates(profile, user_query)
    detail = users_repo.get_user_detail(user_id) if user_id else None
    customer_context = build_customer_context(detail)

    def generate():
        if not matches:
            yield json.dumps({"type": "error", "message": "조건에 맞는 후보를 찾지 못했습니다."}, ensure_ascii=False) + "\n"
            return
        # 답변이 나오기 전에 실제 근거(고객 정보)를 먼저 보여준다 - 답변을
        # 이 사실과 눈으로 대조해서 반증(팩트체크)할 수 있게 하는 게 목적이다.
        yield json.dumps({"type": "customer_facts", "text": customer_context}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "sources", "sources": matches}, ensure_ascii=False) + "\n"
        answer_parts = []
        try:
            for piece in answering.stream(user_query, matches, customer_context):
                answer_parts.append(piece)
                yield json.dumps({"type": "delta", "text": piece}, ensure_ascii=False) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"LLM 응답 실패: {e}"}, ensure_ascii=False) + "\n"
            return
        # 답변을 만든 모델이 아니라 별도 호출로 [고객 정보]와 대조해 정확도를 매긴다 - 반증(팩트체크).
        try:
            verification = answering.verify(detail, "".join(answer_parts))
            yield json.dumps({"type": "verification", **verification}, ensure_ascii=False) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"반증 실패: {e}"}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "done"}, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/ask", dependencies=[Depends(get_current_admin)])
def ask(req: AskRequest):
    """관리자 대시보드용. pet_id 가 오면 그 펫의 DB 프로필을 쓰고, 없으면 요청에 직접 적힌 필터를 쓴다."""
    return _stream_answer(req.user_query, req.pet_id, req.user_id, req.model_dump())


@router.post("/ask/me")
def ask_me(req: AskMeRequest, user_id: int = Depends(get_current_user)):
    """일반 회원용. 로그인한 본인의 첫 번째 펫 프로필로 묻는다 - 회원가입이 강아지 한 마리만
    받으니 지금은 이걸로 충분하다. 펫이 여러 마리가 되면 pet_id 선택 UI가 먼저 필요하다."""
    pets = find_pets_by_user(user_id)
    pet_id = pets[0]["pet_id"] if pets else None
    return _stream_answer(req.user_query, pet_id, user_id)
