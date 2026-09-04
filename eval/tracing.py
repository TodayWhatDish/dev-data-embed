# Last Updated: 2026-09-04

"""채점기가 공유하는 머리말(banner)과 실행 기록(eval_run).

숫자를 화면에만 찍으면 "지난주보다 나아졌나"를 못 따진다. 그렇다고 DB 에 못 쌓는다 -
모델을 바꿔 재색인하면 chunk_vectors 가 통째로 DROP 되기 때문이다(vector_db.py:38).
golden.py 의 save_run() 이 data/eval/*.json 에 남기는 것과 같은 이유로, 실행 기록도
DB 밖(data/eval/runs.jsonl)에 한 줄씩 덧붙인다.

LangSmith 는 켜져 있고 패키지가 깔려 있을 때만 함께 보낸다. 없으면 조용히 통과한다 -
추적이 안 된다고 채점이 멈추면 안 된다. 채점기가 추적보다 위에 있다.
"""
import contextlib
import datetime
import json
import time

from app.core.config import (
    DB_PATH,
    EMBED_DIM,
    EMBED_MODEL,
    EVAL_DIR,
    LANGSMITH_EVAL_PROJECT,
    LANGSMITH_TRACING,
    LLM_MODEL,
    USE_API,
)

try:
    from langsmith import trace as _langsmith_trace
except ImportError:
    _langsmith_trace = None

RUNS_PATH = EVAL_DIR / "runs.jsonl"


def tracing_on() -> bool:
    """LangSmith 로 보낼 수 있는 상태인가. 켜 달랬는데 패키지가 없으면 False 다."""
    return bool(LANGSMITH_TRACING and _langsmith_trace is not None)


_warmed = False


def warm_domain() -> None:
    """마스터 캐시(분류·급여목적·원료·알러지)를 올린다. 채점기는 이걸 직접 해야 한다.

    서버는 기동할 때 lifespan 이 init_from_db() 를 부르지만(api/lifespan.py:32) 채점기는
    서버를 안 띄운다. 안 부르고 features/products.py 를 타면 ProductMgr 이 아직 비어 있어
    '_product_category_hierarchy 가 없다'는 AttributeError 로 죽는다 - 검색 결과를 상품으로
    바꾸는 순간에야 터지므로, 앞의 자가검증은 다 통과한 뒤에 죽는다.

    banner() 가 아니라 따로 두는 이유: 머리말을 찍는 일과 DB 를 읽는 일은 값이 다르다.
    """
    global _warmed
    if _warmed:
        return
    from app.domain.domain_init import init_from_db

    init_from_db()
    _warmed = True


def require_llm() -> bool:
    """LLM 이 실제로 대답하는지 한 번 두들겨 본다. 안 되면 이유를 찍고 False.

    이걸 안 하면 표본 30건짜리 채점이 30번 연달아 ConnectionError 를 뱉고 끝난다 -
    화면이 예외로 뒤덮여 '모델이 안 떠 있다'는 한 줄이 묻힌다. 채점을 시작하기 전에
    한 번만 확인하고, 실패는 실패라고 말한다.
    """
    from app.adapters.stores.llm import chat

    try:
        chat.invoke("ok")
        return True
    except Exception as broke:
        print(f"  LLM 을 못 부른다: {type(broke).__name__}: {broke}")
        print()
        if USE_API:
            print("  USE_API=1 이다. .env 의 LLM_API_KEY / API_MODEL 을 확인한다.")
        else:
            print(f"  로컬 모드다. Ollama 가 떠 있어야 한다:  ollama serve  후  ollama pull {LLM_MODEL}")
            print("  상용 API 로 재려면 .env 에 USE_API=1 과 LLM_API_KEY 를 넣는다.")
        return False


def banner(title: str) -> None:
    """무엇으로 잰 숫자인지를 결과 위에 박아 둔다.

    모델·차원·DB 를 안 적으면 나중에 숫자만 남아 어떤 조건에서 나온 것인지 못 되짚는다.
    """
    print("=" * 74)
    print(title)
    print("=" * 74)
    print(f"  백엔드   {'상용 API' if USE_API else '로컬'}")
    print(f"  LLM      {LLM_MODEL}")
    print(f"  임베딩   {EMBED_MODEL} ({EMBED_DIM}차원)")
    print(f"  DB       {DB_PATH}")

    if tracing_on():
        print(f"  LangSmith 켜짐 · 프로젝트 '{LANGSMITH_EVAL_PROJECT}'")
    elif LANGSMITH_TRACING:
        print("  LangSmith 켜 달랬지만 langsmith 패키지가 없다.  pip install -e \".[trace]\"")
    else:
        print(f"  기록     {RUNS_PATH} (LangSmith 는 꺼짐)")
    print()


class Handle:
    """채점기가 지표를 담아 두는 그릇. record() 로 담은 값이 그대로 기록에 실린다."""

    def __init__(self, run_tree=None):
        self._run_tree = run_tree
        self.outputs: dict = {}

    def record(self, **values) -> None:
        self.outputs.update(values)

    def url(self):
        if self._run_tree is None:
            return None
        try:
            return self._run_tree.get_url()
        except Exception:
            # 추적 주소를 못 얻는 건 채점 실패가 아니다. 주소만 없이 넘어간다.
            return None


def append_run(name: str, inputs: dict, outputs: dict) -> None:
    """실행 한 건을 data/eval/runs.jsonl 에 한 줄 덧붙인다.

    한 줄 = 한 실행이라 나중에 grep 이나 pandas 로 그냥 읽힌다. 덧붙이기만 하므로
    이전 결과를 덮어쓸 일이 없다.
    """
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "name": name,
        "backend": "api" if USE_API else "local",
        "llm": LLM_MODEL,
        "embed": EMBED_MODEL,
        "dim": EMBED_DIM,
        "inputs": inputs,
        "outputs": outputs,
    }
    with RUNS_PATH.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(row, ensure_ascii=False) + "\n")


@contextlib.contextmanager
def eval_run(name: str, inputs: dict | None = None, tags: list | None = None):
    """채점 한 판을 감싼다. 빠져나올 때 걸린 시간을 붙여 기록으로 남긴다.

    채점 도중에 터져도 finally 에서 남긴다 - 절반만 잰 숫자라도 "여기서 죽었다"는
    사실이 남아야 다음에 되짚을 수 있다.
    """
    inputs = inputs or {}
    started = time.perf_counter()
    stamp = datetime.datetime.now().strftime("%m-%d %H:%M")

    if not tracing_on():
        handle = Handle()
        try:
            yield handle
        finally:
            handle.outputs["걸린시간(초)"] = round(time.perf_counter() - started, 1)
            append_run(name, inputs, handle.outputs)
        return

    with _langsmith_trace(
        name=f"{name} ({stamp})",
        run_type="chain",
        inputs=inputs,
        project_name=LANGSMITH_EVAL_PROJECT,
        tags=["eval", name, *(tags or [])],
        metadata={"llm": LLM_MODEL, "embed": EMBED_MODEL, "backend": "api" if USE_API else "local"},
    ) as run_tree:
        handle = Handle(run_tree)
        try:
            yield handle
        finally:
            handle.outputs["걸린시간(초)"] = round(time.perf_counter() - started, 1)
            append_run(name, inputs, handle.outputs)
            run_tree.add_outputs(handle.outputs)

    address = handle.url()
    if address:
        print(f"\n  LangSmith  {address}")


@contextlib.contextmanager
def detached():
    """바깥 추적 트리에서 떼어 낸다. 남의 트리를 자기 부모로 삼는 라이브러리(ragas)용."""
    if not tracing_on():
        yield
        return

    from langsmith import tracing_context

    with tracing_context(parent=False):
        yield
