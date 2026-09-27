"""ask 그래프 조립과 실행. /ask, /ask/me 가 ask_stream() 으로 여기에 모인다.

    START ┬─ plan ─────┬→ run_tools ─(후보 없음)→ END
          └─ retrieve ─┘       └→ generate ─(LLM 실패)→ END
                                      └→ check → END

plan(LLM) 과 retrieve(검색·DB) 는 서로의 결과를 안 쓰므로 동시에 출발한다 - plan 의 LLM 왕복이
검색 시간에 가려진다. run_tools 는 둘을 다 기다린다(성분표 조회에 후보 product_id 가 필요하다).
"""

import json
import logging
from typing import Iterator

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes import (
    check,
    generate,
    plan,
    retrieve,
    route_after_generate,
    route_after_tools,
    run_tools,
)
from app.graph.state import AskState

logger = logging.getLogger(__name__)

ERROR_MESSAGE = "답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."


def build_ask_graph() -> CompiledStateGraph:
    builder = StateGraph(AskState)
    builder.add_node("plan", plan)
    builder.add_node("retrieve", retrieve)
    builder.add_node("run_tools", run_tools)
    builder.add_node("generate", generate)
    builder.add_node("check", check)

    builder.add_edge(START, "plan")
    builder.add_edge(START, "retrieve")
    # 리스트로 넘기면 둘 다 끝나야 run_tools 가 한 번 돈다 (각각 따로 잇으면 두 번 돈다)
    builder.add_edge(["plan", "retrieve"], "run_tools")
    builder.add_conditional_edges("run_tools", route_after_tools, ["generate", END])
    builder.add_conditional_edges("generate", route_after_generate, ["check", END])
    builder.add_edge("check", END)
    return builder.compile()


ask_graph = build_ask_graph()


def ask_stream(
    user_query: str, pet_id: int | None, user_id: int | None, profile_filters: dict | None = None
) -> Iterator[str]:
    """그래프를 돌리며 노드가 쓴 이벤트를 NDJSON 한 줄씩 흘려보낸다."""
    state = {"question": user_query, "pet_id": pet_id, "user_id": user_id, "profile_filters": profile_filters}
    try:
        for event in ask_graph.stream(state, stream_mode="custom"):
            yield json.dumps(event, ensure_ascii=False) + "\n"
    except Exception:
        logger.exception("ask 그래프 실패")
        yield json.dumps({"type": "error", "message": ERROR_MESSAGE}, ensure_ascii=False) + "\n"