"""ask 그래프의 노드. 각 노드는 NDJSON 이벤트를 get_stream_writer() 로 흘려보낸다."""

import logging

from langgraph.config import get_stream_writer
from langgraph.graph import END

from app.core.trace import log_customer_question
from app.domain.prompting import build_customer_context
from app.graph.state import AskState
from app.repositories import users as users_repo
from app.services.answering import stream, verify
from app.services.profile import build_profile, pet_profile
from app.services.searching import candidates

logger = logging.getLogger(__name__)


def _log(state: AskState, **kw) -> None:
    log_customer_question(user_id=state.get("user_id"), pet_id=state.get("pet_id"), user_query=state["question"], **kw)


def retrieve(state: AskState) -> dict:
    """프로필 -> 후보 검색 -> 고객 정보. 근거(customer_facts, sources)를 답변보다 먼저 보낸다."""
    write = get_stream_writer()
    pet_id = state.get("pet_id")
    profile = pet_profile(pet_id) if pet_id else build_profile(state.get("profile_filters") or {})
    matches = candidates(profile, state["question"])
    detail = users_repo.get_user_detail(state["user_id"]) if state.get("user_id") else None
    customer_context = build_customer_context(detail)

    if not matches:
        _log(state, matches=[], answer="", ok=False, error="후보 없음")
        write({"type": "error", "message": "조건에 맞는 후보를 찾지 못했습니다."})
    else:
        write({"type": "customer_facts", "text": customer_context})
        write({"type": "sources", "sources": matches})
    return {"matches": matches, "detail": detail, "customer_context": customer_context}


def generate(state: AskState) -> dict:
    """답변을 글자 조각(delta)으로 흘려보내고 질문 기록을 남긴다."""
    write = get_stream_writer()
    parts = []
    try:
        for piece in stream(state["question"], state["matches"], state["customer_context"]):
            parts.append(piece)
            write({"type": "delta", "text": piece})
    except Exception as e:
        # 원문(키·스택이 섞일 수 있다)은 서버 로그와 질문 기록에만, 클라이언트엔 고정 문구만
        logger.exception("LLM 답변 스트리밍 실패")
        _log(state, matches=state["matches"], answer="".join(parts), ok=False, error=str(e))
        write({"type": "error", "message": "답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."})
        return {"answer": "".join(parts), "failed": True}
    _log(state, matches=state["matches"], answer="".join(parts), ok=True)
    return {"answer": "".join(parts)}


def check(state: AskState) -> dict:
    """답변을 만든 모델과 다른 모델로 반증(팩트체크)한다."""
    write = get_stream_writer()
    try:
        write({"type": "verification", **verify(state.get("detail"), state["answer"])})
    except Exception:
        logger.exception("반증(팩트체크) 실패")
        write({"type": "error", "message": "답변 검증에 실패했습니다."})
    write({"type": "done"})
    return {}


def route_after_retrieve(state: AskState) -> str:
    return "generate" if state["matches"] else END


def route_after_generate(state: AskState) -> str:
    return END if state.get("failed") else "check"