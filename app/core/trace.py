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
        self._write({
            "type": "llm_call", "ok": False,
            "time": datetime.now().isoformat(timespec="seconds"),
            "run_id": str(run_id),
            "seconds": round(time.perf_counter() - started, 2) if started else None,
            "error": str(error)[:200],
        })

    def _write(self, row: dict) -> None:
        # ponytail: query_log.jsonl이 무한정 커진다 - 회전이 필요해지면
        # rag-project-cleanup/app/core/trace.py의 JsonlTracer._rotate() 참고
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


tracer = JsonlTracer()


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

    print("JsonlTracer 자체 점검 통과")


if __name__ == "__main__":
    _demo()
