# Last updated: 2026-09-03

"""candidates()가 찾아준 후보 리뷰를 근거로, 자유 텍스트 답변을 조각조각 스트리밍하는 자리.
구조화 출력(추천)과 달리 여기는 형식 검증이 없다 - 자유 문장이라 검증할 스키마가 없기 때문이다.
"""

import json
import logging
from typing import Any, Iterator

from langchain_core.output_parsers import StrOutputParser

from app.adapters.llm import get_chat_answer, get_chat_verify
from app.core.trace import log_customer_question
from app.domain.prompting import (
    ANSWER_PROMPT,
    FactCheck,
    build_answer_context,
    build_customer_context,
    build_factcheck_prompt,
)
from app.repositories import users as users_repo
from app.services.profile import build_profile, pet_profile
from app.services.searching import candidates

logger = logging.getLogger(__name__)


def ask_stream(
    user_query: str, pet_id: int | None, user_id: int | None, profile_filters: dict | None = None
) -> Iterator[str]:
    """profile 구성 -> 후보 검색 -> 답변 스트리밍 -> 반증 순서로 엮어 NDJSON 줄을 흘려보낸다.
    /ask, /ask/me 둘 다 여기로 모인다.

    pet_id 가 오면 그 펫의 DB 프로필을 쓴다. 없으면 profile_filters(요청에 직접 적힌 필터)를 쓴다.
    준비(검색·고객 조회)는 스트림 시작 전에 끝낸다 - 여기서 터지면 깨진 스트림이 아니라 500이 된다.
    """
    profile = pet_profile(pet_id) if pet_id else build_profile(profile_filters or {})
    matches = candidates(profile, user_query)
    detail = users_repo.get_user_detail(user_id) if user_id else None
    customer_context = build_customer_context(detail)

    def generate():
        if not matches:
            log_customer_question(
                user_id=user_id,
                pet_id=pet_id,
                user_query=user_query,
                matches=[],
                answer="",
                ok=False,
                error="후보 없음",
            )
            yield (
                json.dumps(
                    {"type": "error", "message": "조건에 맞는 후보를 찾지 못했습니다."}, ensure_ascii=False
                )
                + "\n"
            )
            return
        # 답변이 나오기 전에 실제 근거(고객 정보)를 먼저 보여준다 - 답변을
        # 이 사실과 눈으로 대조해서 반증(팩트체크)할 수 있게 하는 게 목적이다.
        yield json.dumps({"type": "customer_facts", "text": customer_context}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "sources", "sources": matches}, ensure_ascii=False) + "\n"
        answer_parts = []
        try:
            for piece in stream(user_query, matches, customer_context):
                answer_parts.append(piece)
                yield json.dumps({"type": "delta", "text": piece}, ensure_ascii=False) + "\n"
        except Exception as e:
            # 원문(키·스택이 섞일 수 있다)은 서버 로그와 관리자용 질문 기록에만 남기고, 클라이언트엔 고정 문구만 보낸다
            logger.exception("LLM 답변 스트리밍 실패")
            log_customer_question(
                user_id=user_id,
                pet_id=pet_id,
                user_query=user_query,
                matches=matches,
                answer="".join(answer_parts),
                ok=False,
                error=str(e),
            )
            yield json.dumps({"type": "error", "message": "답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."}, ensure_ascii=False) + "\n"
            return
        # 관리자 대시보드 '질문' 탭용 기록 - 반증 성패와 무관하게 답변이 나왔으면 성공으로 남긴다.
        log_customer_question(
            user_id=user_id,
            pet_id=pet_id,
            user_query=user_query,
            matches=matches,
            answer="".join(answer_parts),
            ok=True,
        )
        # 답변을 만든 모델이 아니라 별도 호출로 [고객 정보]와 대조해 정확도를 매긴다 - 반증(팩트체크).
        try:
            verification = verify(detail, "".join(answer_parts))
            yield json.dumps({"type": "verification", **verification}, ensure_ascii=False) + "\n"
        except Exception:
            logger.exception("반증(팩트체크) 실패")
            yield json.dumps({"type": "error", "message": "답변 검증에 실패했습니다."}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "done"}, ensure_ascii=False) + "\n"

    return generate()


def stream(
    user_query: str, candidates: list[dict[str, Any]], customer_context: str = "정보 없음"
) -> Iterator[str]:
    """검색 후보와 실제 고객 구매 이력을 분리된 슬롯으로 넘기고, 모델이 흘려보내는 글자 조각을 그대로 다시 흘려보낸다."""
    context = build_answer_context(candidates)
    chain = ANSWER_PROMPT | get_chat_answer() | StrOutputParser()
    yield from chain.stream(
        {"context": context, "customer_context": customer_context, "question": user_query}
    )


def verify(detail: dict[str, Any] | None, answer: str) -> dict[str, Any]:
    """1차: 문자열 대조(공짜, 즉시) - 펫 이름이 답변에 등장하는지만 본다.
    2차: 대조할 실제 고객 정보(detail)가 있으면, 질문이 뭐든 상관없이 항상 LLM 채점도 돌린다.

    ponytail: "의심될 때만 LLM"으로 키워드 트리거를 쓰다가 뺐다 - 질문 종류가 늘어날 때마다
    키워드를 계속 추가해야 해서 범용 질문을 못 커버한다. 판단 대상이 범용적(자유 질문)이면
    판단 주체도 범용적(LLM)이어야 한다 - 대신 대조할 정보가 없는 요청(user_id 없음)은 건너뛴다.
    상품명 grounding은 뺐다 - [추천 후보](안 산 상품)를 언급하는 게 정상 동작이라
    문자열만 보고는 정상 추천/오답을 못 가른다.
    """
    known_pets = {p["name"] for p in (detail["pets"] if detail else [])}
    mentioned_pets = [name for name in known_pets if name in answer]
    accuracy = len(mentioned_pets) / len(known_pets) if known_pets else 1.0
    result: dict[str, Any] = {
        "accuracy": accuracy,
        "note": f"실제 펫 이름 언급: {', '.join(mentioned_pets)}"
        if mentioned_pets
        else "답변에서 이 고객의 펫 이름이 확인되지 않음",
        "grounded_pets": mentioned_pets,
        "llm_checked": False,
    }

    if detail:
        customer_context = build_customer_context(detail)
        prompt = build_factcheck_prompt(customer_context, answer)
        verifier = get_chat_verify().with_structured_output(FactCheck).with_retry(stop_after_attempt=3)
        judged: FactCheck = verifier.invoke(prompt)
        result.update(judged.model_dump())
        result["llm_checked"] = True

    return result
