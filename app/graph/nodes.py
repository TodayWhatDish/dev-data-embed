"""ask 그래프의 노드. 각 노드는 NDJSON 이벤트를 get_stream_writer() 로 흘려보낸다.

DB 세션은 상태(state)가 아니라 실행 설정(config["configurable"]["db"])으로 받는다 - 상태는 노드가
주고받는 값이고, 세션은 라우트의 Depends(get_db) 가 빌려준 실행 도구다.
"""

import logging

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END
from sqlalchemy.orm import Session

from app.domain.prompting import build_customer_context
from app.graph.state import AskState
from app.repositories import products as products_repo
from app.repositories import users as users_repo
from app.services.answering import plan_tools, stream, verify
from app.services.profile import build_profile, pet_profile
from app.services.questions import log_customer_question
from app.services.searching import candidates

logger = logging.getLogger(__name__)


def _db(config: RunnableConfig) -> Session:
    return config["configurable"]["db"]


def _log(db: Session, state: AskState, **kw) -> None:
    if not state.get("log_question", True):
        return
    log_customer_question(db, user_id=state.get("user_id"), pet_id=state.get("pet_id"), user_query=state["question"], **kw)


def plan(state: AskState) -> dict:
    """질문만 보고 부를 도구를 고른다. retrieve 와 다른 스레드에서 동시에 돌므로 DB 를 만지지 않는다."""
    try:
        return {"tools": plan_tools(state["question"])}
    except Exception:
        # 계획이 실패해도 답변은 나가야 한다 - 도구 없이 진행
        logger.exception("plan 실패, 도구 없이 진행")
        return {"tools": []}


def retrieve(state: AskState, config: RunnableConfig) -> dict:
    """프로필 -> 후보 검색 -> 고객 정보. 근거(customer_facts, sources)를 답변보다 먼저 보낸다."""
    write = get_stream_writer()
    db = _db(config)
    pet_id = state.get("pet_id")
    profile = pet_profile(db, pet_id) if pet_id else build_profile(state.get("profile_filters") or {})
    matches = candidates(db, profile, state["question"])
    detail = users_repo.get_user_detail(db, state["user_id"]) if state.get("user_id") else None
    customer_context = build_customer_context(detail)

    if not matches:
        _log(db, state, matches=[], answer="", ok=False, error="후보 없음")
        write({"type": "error", "message": "조건에 맞는 후보를 찾지 못했습니다."})
    else:
        write({"type": "customer_facts", "text": customer_context})
        # 점수 0 = 질문과 무관한 후보(날씨 질문 등). LLM 엔 그대로 주되 화면엔 '매칭 0%' 카드로 안 띄운다
        write({"type": "sources", "sources": [m for m in matches if m["score"] > 0]})
    return {"matches": matches, "detail": detail, "customer_context": customer_context}


def run_tools(state: AskState, config: RunnableConfig) -> dict:
    """plan 과 retrieve 가 둘 다 끝난 뒤 돈다. 성분표는 검색된 후보 상품만 조회한다."""
    if "nutrition" not in state.get("tools", []) or not state["matches"]:
        return {"nutritions": None}
    product_ids = list(dict.fromkeys(m["product_id"] for m in state["matches"]))
    nutritions = products_repo.find_nutritions(_db(config), product_ids)
    get_stream_writer()({"type": "tool_result", "tool": "nutrition", "data": nutritions})
    return {"nutritions": nutritions}


def generate(state: AskState, config: RunnableConfig) -> dict:
    """답변을 글자 조각(delta)으로 흘려보내고 질문 기록을 남긴다."""
    write = get_stream_writer()
    db = _db(config)
    parts = []
    try:
        for piece in stream(state["question"], state["matches"], state["customer_context"], state.get("nutritions")):
            parts.append(piece)
            write({"type": "delta", "text": piece})
    except Exception as e:
        # 원문(키·스택이 섞일 수 있다)은 서버 로그와 질문 기록에만, 클라이언트엔 고정 문구만
        logger.exception("LLM 답변 스트리밍 실패")
        _log(db, state, matches=state["matches"], answer="".join(parts), ok=False, error=str(e))
        write({"type": "error", "message": "답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."})
        return {"answer": "".join(parts), "failed": True}
    _log(db, state, matches=state["matches"], answer="".join(parts), ok=True)
    return {"answer": "".join(parts)}


def check(state: AskState) -> dict:
    """답변을 만든 모델과 다른 모델로 반증(팩트체크)한다."""
    write = get_stream_writer()
    try:
        write({"type": "verification", **verify(state.get("detail"), state["answer"], state["matches"], state.get("nutritions"))})
    except Exception:
        logger.exception("반증(팩트체크) 실패")
        write({"type": "error", "message": "답변 검증에 실패했습니다."})
    write({"type": "done"})
    return {}


def route_after_tools(state: AskState) -> str:
    return "generate" if state["matches"] else END


def route_after_generate(state: AskState) -> str:
    return END if state.get("failed") else "check"