# Last updated: 2026-09-03
# Last Updated : 2026-09-03

""" LLM 호출 하나하나를 logs/query_log.jsonl 에 한 줄씩 남기는 LangChain 콜백.

    app/adapters/stores/llm.py 가 chat/chat_answer 를 만들 때 이 tracer 를 꽂아 두면,
    features/* 가 어떤 프로바이더를 부르든(anthropic/openai 호환) 호출마다 자동으로
    걸린 시간·토큰 수·성공 여부가 남는다. 지금까지는 app/query.py(CLI)만 수동으로
    로그를 남겨서, API 경로(ask.py/recommend.py)로 들어온 호출은 기록이 전혀 없었다.
"""
import json
import time
from datetime import datetime

from langchain_core.callbacks import BaseCallbackHandler

from app.core.config import LOG_PATH


def _tokens_of(response) -> tuple:
    """응답에서 입력/출력 토큰 수와 모델 이름을 꺼낸다.

    프로바이더마다 사용량이 붙는 자리가 달라(llm_output vs usage_metadata) 두 곳을 다 본다.
    """
    token_usage = (response.llm_output or {}).get("token_usage") or {}
    generation = response.generations[0][0] if response.generations else None
    meta = getattr(getattr(generation, "message", None), "usage_metadata", None) or {}
    return (
        token_usage.get("prompt_tokens") or meta.get("input_tokens"),
        token_usage.get("completion_tokens") or meta.get("output_tokens"),
        (response.llm_output or {}).get("model_name"),
    )


class JsonlTracer(BaseCallbackHandler):
    """모델 호출의 시작/끝을 가로채 한 줄씩 남긴다. run_id로 시작/끝을 짝짓는다."""

    def __init__(self, path=LOG_PATH):
        self.path = path
        self.started: dict = {}  # run_id -> 시작 시각. 요청이 겹쳐도 서로 안 섞이게 나눠 둔다.

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs) -> None:
        self.started[run_id] = time.perf_counter()

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        started = self.started.pop(run_id, None)
        in_tokens, out_tokens, model = _tokens_of(response)
        self._write({
            "type": "llm_call", "ok": True,
            "time": datetime.now().isoformat(timespec="seconds"),
            "run_id": str(run_id), "model": model,
            "seconds": round(time.perf_counter() - started, 2) if started else None,
            "prompt_tokens": in_tokens, "completion_tokens": out_tokens,
        })

    def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        started = self.started.pop(run_id, None)
        # anthropic.APIConnectionError 등은 str(error)가 "Connection error."로 뭉뚱그려지고,
        # with_retry()가 감싸면 __cause__도 같은 종류의 껍데기라 한 겹만 봐선 안 보인다 -
        # 진짜 원인(httpx.ConnectError 등)이 나올 때까지 체인을 끝까지 타고 내려간다.
        chain = []
        cur = getattr(error, "__cause__", None)
        while cur is not None and len(chain) < 5:
            chain.append(repr(cur)[:200])
            cur = getattr(cur, "__cause__", None)
        self._write({
            "type": "llm_call", "ok": False,
            "time": datetime.now().isoformat(timespec="seconds"),
            "run_id": str(run_id),
            "seconds": round(time.perf_counter() - started, 2) if started else None,
            "error": str(error)[:200],
            "cause_chain": chain,
        })

    def _write(self, row: dict) -> None:
        # ponytail: query_log.jsonl이 무한정 커진다 - 회전이 필요해지면
        # rag-project-cleanup/app/core/trace.py의 JsonlTracer._rotate() 참고
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


tracer = JsonlTracer()


def log_customer_question(*, user_id: int | None, pet_id: int | None, user_query: str,
                           matches: list[dict], answer: str, ok: bool,
                           error: str | None = None, path=LOG_PATH) -> None:
    """/ask, /ask/me 로 들어온 질문 한 건을 남긴다. 관리자 대시보드 '질문' 탭이 이 줄들을 읽는다."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "type": "customer_question",
            "time": datetime.now().isoformat(timespec="seconds"),
            "user_id": user_id, "pet_id": pet_id,
            "user_query": user_query,
            "matched": [{"product_id": m["product_id"], "name": m["name"],
                         "product_type": m.get("product_type"), "score": m["score"]}
                        for m in matches],
            "answer": answer, "ok": ok, "error": error,
        }, ensure_ascii=False) + "\n")


def read_customer_questions(limit: int = 50, path=LOG_PATH) -> list[dict]:
    """최근 질문부터 최대 limit개.

    ponytail: 매번 파일 전체를 스캔한다 - query_log.jsonl이 커져서 느려지면
    tail만 읽도록 바꿀 것.
    """
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # JsonlTracer 이전에 남은 옛 pretty-print 로그 등 - 한 줄 = 한 JSON이 아닌 것은 건너뛴다
                if row.get("type") == "customer_question":
                    rows.append(row)
    except FileNotFoundError:
        return []
    rows.reverse()
    return rows[:limit]


def _demo() -> None:
    """실제 LLM 호출 없이, on_chat_model_start/on_llm_end/on_llm_error가 한 줄씩 남기는지 확인한다."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        test_tracer = JsonlTracer(path=tmp.name)

    class FakeResponse:
        llm_output = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}, "model_name": "test-model"}
        generations = []

    test_tracer.on_chat_model_start({}, [], run_id="run-1")
    test_tracer.on_llm_end(FakeResponse(), run_id="run-1")
    with open(test_tracer.path, encoding="utf-8") as f:
        row = json.loads(f.readline())
    assert row["ok"] is True
    assert row["prompt_tokens"] == 10 and row["completion_tokens"] == 5
    assert row["model"] == "test-model"
    assert "run-1" not in test_tracer.started  # 짝지어지면 지워져야 한다

    test_tracer.on_chat_model_start({}, [], run_id="run-2")
    test_tracer.on_llm_error(RuntimeError("boom"), run_id="run-2")
    with open(test_tracer.path, encoding="utf-8") as f:
        err_row = json.loads(f.readlines()[-1])
    assert err_row["ok"] is False and "boom" in err_row["error"]

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp2:
        q_path = tmp2.name
    log_customer_question(user_id=1, pet_id=2, user_query="사료 추천해줘",
                           matches=[{"product_id": 9, "name": "테스트사료", "product_type": "사료", "score": 0.9}],
                           answer="테스트사료 추천합니다.", ok=True, path=q_path)
    rows = read_customer_questions(path=q_path)
    assert len(rows) == 1 and rows[0]["user_query"] == "사료 추천해줘"
    assert rows[0]["matched"][0]["product_type"] == "사료"

    print("JsonlTracer 자체 점검 통과")


if __name__ == "__main__":
    _demo()
