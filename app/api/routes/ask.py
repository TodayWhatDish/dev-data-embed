# Last Updated : 2026-09-01

""" 관리자/운영자가 사용자 질문을 바로 테스트할 수 있게 하는 API.

    이 파일은 웹 대시보드에서 사용자의 질문을 입력하고,
    현재 검색/추천/LLM 흐름이 실제로 동작하는지 빠르게 검증하기 위한
    스트리밍 엔드포인트를 제공한다.

    - 질문을 받는다
    - 프로필과 후보를 구성한다
    - 답변을 스트리밍으로 전달한다
    - 데이터가 없으면 에러 메시지를 NDJSON으로 반환한다
"""

import json 

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.schemas import AskRequest
from app.core.auth import get_current_admin
from app.domain.prompting import build_customer_context
from app.features import answering
from app.features.profile import build_profile, pet_profile
from app.features.searching import candidates
from app.features.customers import customer_detail

router = APIRouter(dependencies=[Depends(get_current_admin)])

@router.post("/ask")
def ask(req: AskRequest):
    """profile 구성 -> 후보 검색 -> 답변 스트리밍 순서로 엮는다.

    pet_id 가 오면 그 펫의 DB 프로필을 쓴다(관리자 대시보드가 이 경로).
    없으면 요청에 직접 적힌 필터를 쓴다.
    """
    profile = pet_profile(req.pet_id) if req.pet_id else build_profile(req.model_dump())
    matches = candidates(profile, req.user_query)
    customer_context = build_customer_context(customer_detail(req.user_id) if req.user_id else None)

    def generate():
        if not matches:
            yield json.dumps({"type": "error", "message": "조건에 맞는 후보를 찾지 못했습니다."}, ensure_ascii=False) + "\n"
            return
        # 답변이 나오기 전에 실제 근거(고객 정보)를 먼저 보여준다 - 관리자가 아래 답변을
        # 이 사실과 눈으로 대조해서 반증(팩트체크)할 수 있게 하는 게 목적이다.
        yield json.dumps({"type": "customer_facts", "text": customer_context}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "sources", "sources": matches}, ensure_ascii=False) + "\n"
        answer_parts = []
        try:
            for piece in answering.stream(req.user_query, matches, customer_context):
                answer_parts.append(piece)
                yield json.dumps({"type": "delta", "text": piece}, ensure_ascii=False) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"LLM 응답 실패: {e}"}, ensure_ascii=False) + "\n"
            return
        # 답변을 만든 모델이 아니라 별도 호출로 [고객 정보]와 대조해 정확도를 매긴다 - 반증(팩트체크).
        try:
            verification = answering.verify(customer_context, "".join(answer_parts))
            yield json.dumps({"type": "verification", **verification}, ensure_ascii=False) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"반증 실패: {e}"}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "done"}, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")