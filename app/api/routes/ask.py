# Last Updated : 2026-09-01

"""질문을 받아 답변을 NDJSON 형식으로 한 줄씩 전송한다."""

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