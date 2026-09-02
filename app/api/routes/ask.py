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

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import AskRequest
from app.features import answering
from app.features.profile import build_profile
from app.features.searching import candidates

router = APIRouter()

@router.post("/ask")
def ask(req: AskRequest):
    """profile 구성 -> 후보 검색 -> 답변 스트리밍 순서로 엮는다."""
    profile = build_profile(req.model_dump())
    matches = candidates(profile, req.user_query)
    if not matches:
        yield json.dumps({"error": "조건에 맞는 후보를 찾지 못했습니다."}) + "\n"
        return

    def generate():
        yield json.dumps({"type": "sources", "sources": matches}, ensure_ascii=False) + "\n"
        for piece in answering.stream(req.user_query, matches):
            yield json.dumps({"type":"delta","text":piece}, ensure_ascii=False) + "\n"
        yield json.dumps({"type":"done"}, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")