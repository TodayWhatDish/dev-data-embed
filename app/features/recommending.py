# Last Updated : 2026-08-30

""" products.py가 좁혀준 후보 안에서만 LLM이 고르도록 강제하고, 형식 깨진 응답을 재시도로 잡는 자리.
    이 검증이 없으면 LLM이 후보에 없는 상품을 지어내도 그대로 나감.
"""
import json
import re
from typing import Any

from app.adapters.stores.llm import chat
from app.domain.prompting import build_messages

MAX_RETRIES = 2

# 코드블록으로 감싸 오는 버릇이 있는 모델이 많다. 형식 위반으로 퇴짜놓기 전에 벗겨본다 —
# 내용이 맞는데 울타리 세 글자 때문에 재시도를 쓰는 건 아깝다.
FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def parse_answer(text: str) -> dict[str, Any]:
    """모델 응답 문자열을 dict 로. 못 읽으면 ValueError 를 던진다.

    JSON 앞뒤에 말을 덧붙이는 경우가 잦아서, 벗겨낸 뒤에도 실패하면 첫 '{' 부터
    마지막 '}' 까지를 잘라 한 번 더 시도한다. 그래도 안 되면 재시도로 넘긴다.
    """
    stripped = FENCE.sub("", text.strip())
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("JSON 을 찾을 수 없다")
        try:
            parsed = json.loads(stripped[start:end + 1])
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 파싱 실패: {e}")

    if not isinstance(parsed, dict):
        raise ValueError("최상위가 객체가 아니다")
    return parsed


def validate(parsed: dict[str, Any], allowed: set[str], n_pick: int) -> dict[str, Any]:
    """후보 밖 상품을 걸러낸다. 이 함수가 이 파일의 존재 이유다.

    ID 를 지어냈는지만 보는 게 아니라, 형태가 어긋난 항목(문자열이 아닌 product_id,
    picks 가 배열이 아님)도 여기서 막는다. 라우트까지 흘려보내면 응답 직렬화
    시점에 터지는데, 그때는 무엇이 잘못됐는지가 스택트레이스에 안 남는다.
    """
    picks = parsed.get("picks", [])
    if not isinstance(picks, list):
        raise ValueError("picks 가 배열이 아니다")

    clean = []
    for item in picks:
        if not isinstance(item, dict):
            raise ValueError("picks 항목이 객체가 아니다")
        pid = item.get("product_id")
        if not isinstance(pid, str):
            raise ValueError("product_id 가 문자열이 아니다")
        if pid not in allowed:
            # 후보에 없는 ID 는 모델이 지어낸 것이다. 조용히 버리지 않고 재시도를 부른다.
            raise ValueError(f"후보에 없는 product_id: {pid}")
        evidence = item.get("evidence", [])
        clean.append({
            "product_id": pid,
            "reason": str(item.get("reason", "")).strip(),
            "evidence": [str(e) for e in evidence] if isinstance(evidence, list) else [],
        })

    answer = parsed.get("answer", "")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("answer 가 비어 있다")

    # n_pick 초과는 재시도할 만한 잘못이 아니다. 규칙은 '최대'라 넘친 만큼만 자른다.
    return {"answer": answer.strip(), "picks": clean[:n_pick]}


def recommend(question: str, candidates: list[dict[str, Any]], profile: dict[str, Any],
              n_pick: int = 3) -> tuple[Any, int, str]:
    """후보 중에 n_pick개 만큼 고른 결과와 재시도 횟수, 마지막 오류를 돌려준다.

    후보가 비면 모델을 부르지 않는다. 빈 목록을 넘기면 "고를 게 없다"는 답을
    받자고 토큰과 대기 시간을 쓰는 셈이고, 작은 모델은 그 상황에서 오히려
    상품을 지어내기 쉽다.
    """
    if not candidates:
        return {"answer": "조건에 맞는 상품을 찾지 못했습니다.", "picks": []}, 0, ""

    allowed = {c["product_id"] for c in candidates}
    repair, last_error = "", ""

    # 첫 시도 1회 + 재시도 MAX_RETRIES 회.
    for attempt in range(MAX_RETRIES + 1):
        messages = build_messages(question, profile, candidates, n_pick, repair)
        try:
            raw = chat.invoke(messages).content
            return validate(parse_answer(raw), allowed, n_pick), attempt, ""
        except ValueError as e:
            # 형식/규칙 위반. 무엇이 틀렸는지 붙여서 다시 묻는다.
            last_error = str(e)
            repair = last_error
        except Exception as e:
            # 연결 실패 등은 다시 물어도 같은 결과다. 여기서 멈춘다.
            return None, attempt, f"{type(e).__name__}: {e}"

    return None, MAX_RETRIES, last_error
