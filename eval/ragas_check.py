# Last Updated: 2026-09-04

"""답변이 근거에 충실한가.  python -m eval ragas_check [--limit N]

qa_check 와 golden 은 '검색이 맞는 걸 가져왔나'까지만 본다. 그 후보를 받아
answering.stream() 이 만든 자유 문장은 아무도 안 재고 있었다. 검색이 완벽해도
답변이 근거에 없는 말을 지어내면 서비스는 망한 것이다.

두 겹으로 잰다.

  1. 문자열 대조 (공짜, 즉시)
     답변이 언급한 상품명이 후보 목록 안에 있나. 후보에 없는 상품명이 나오면
     그건 지어낸 것이다. LLM 심판이 필요 없는 확실한 지표라 먼저 본다.

  2. ragas 심판 (요금)
     faithfulness        답변의 주장이 근거로 뒷받침되나
     answer_relevancy    답변이 질문에 맞는 말인가
     context_precision   가져온 근거가 실제로 쓸모 있었나

심판도 LLM 이라 틀린다. 점수가 낮으면 '우리 답이 나쁜 것'인지 '심판이 헛짚은 것'인지
부터 가려야 한다 - 그래서 1번(사람이 검산할 수 있는 지표)을 같이 찍는다.
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(errors="replace")

try:
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics._answer_relevance import ResponseRelevancy
    from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference
    from ragas.metrics._faithfulness import Faithfulness

    RAGAS_MISSING = None
except ImportError as why:
    RAGAS_MISSING = why

from langchain_core.embeddings import Embeddings

from app.adapters.stores.llm import chat_verify
from app.core.config import EMBED_MODEL, LLM_MODEL, VERIFY_MODEL
from app.core.embedder import embed_documents, embed_query
from app.features import answering
from app.features.searching import candidates as search_candidates
from pipeline.vector_db import connect

from eval.tracing import banner, detached, eval_run, require_llm, warm_domain

GOLDEN = json.loads((Path(__file__).parent / "qa_golden.json").read_text(encoding="utf-8"))

K = 5


class LocalEmbeddings(Embeddings):
    """ragas 가 요구하는 LangChain Embeddings 모양으로 우리 임베딩 싱글톤을 감싼다.

    langchain_huggingface 로 새로 만들면 같은 모델을 메모리에 두 번 올린다.
    색인·검색·채점이 같은 벡터 공간을 봐야 하는 것도 이유다.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return embed_query(text)


def answer_one(question: str, profile: dict) -> tuple[str, list[dict]]:
    """실제 배포 경로 그대로 답을 만든다. 채점 전용 경로를 따로 두면 배포된 걸 안 재게 된다."""
    cands = search_candidates(profile, question, limit=K)
    answer = "".join(answering.stream(question, cands))
    return answer, cands


def product_names(con) -> dict[int, str]:
    """product_id -> 상품명. 답변에 나온 이름이 후보 밖인지 가리는 데 쓴다."""
    return {pid: name for pid, name in con.execute("SELECT product_id, name FROM product")}


def check_grounding(answer: str, cands: list[dict], all_names: dict[int, str]) -> dict:
    """LLM 없이 답변의 상품 언급을 후보와 대조한다.

    '후보 밖 상품을 말했다'는 심판이 필요 없는 사실이다. faithfulness 가 낮게 나왔을 때
    심판을 의심할지 우리 답을 의심할지, 이 칸이 먼저 답해 준다.
    """
    cand_names = {c["name"] for c in cands}
    mentioned = {name for name in all_names.values() if name in answer}
    return {
        "n_mentioned": len(mentioned),
        "n_from_candidates": len(mentioned & cand_names),
        "n_invented": len(mentioned - cand_names),
        "invented": sorted(mentioned - cand_names),
    }


def main(argv: list[str]) -> int:
    if RAGAS_MISSING is not None:
        print("ragas 를 못 불러왔다.")
        print()
        print('  pip install -e ".[eval]"')
        print()
        print("  기본 설치에 안 넣은 이유: ragas 는 pandas 와 datasets 를 끌고 와서")
        print("  100개 넘는 패키지가 딸려 온다. 서버를 돌리는 데는 하나도 필요 없다.")
        print(f"  (원래 오류: {RAGAS_MISSING})")
        return 3

    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    items = GOLDEN["items"][:limit]

    banner("답변 품질 (ragas_check)")
    if not require_llm():
        return 2
    warm_domain()

    print("=" * 74)
    print(f"문항 {len(items)}개 · 근거 {K}개 · 답변 {LLM_MODEL} · 심판 {VERIFY_MODEL}")
    print("=" * 74)
    print("  문항 하나에 답변 1번 + 심판 여러 번이다. 표본을 작게 잡는다.")
    print()

    con = connect()
    try:
        all_names = product_names(con)
    finally:
        con.close()

    with eval_run("ragas_check", inputs={"문항": len(items), "근거": K}) as run:
        samples, grounding = [], []
        for n, item in enumerate(items, start=1):
            answer, cands = answer_one(item["question"], item["profile"])
            grounding.append(check_grounding(answer, cands, all_names))
            print(f"  {n}/{len(items)}  {item['question'][:44]}")
            samples.append(
                SingleTurnSample(
                    user_input=item["question"],
                    retrieved_contexts=[c["review"] for c in cands],
                    response=answer,
                )
            )

        print()
        print("=" * 74)
        print("1. 후보 밖 상품을 말했나 (문자열 대조, 공짜)")
        print("=" * 74)
        invented = sum(g["n_invented"] for g in grounding)
        mentioned = sum(g["n_mentioned"] for g in grounding)
        print(f"  상품 언급 {mentioned}건 중 후보 밖 {invented}건")
        for item, g in zip(items, grounding):
            if g["n_invented"]:
                print(f"      {item['id']}번: {g['invented']}")
        if not invented:
            print("  후보에 없는 상품은 안 지어냈다.")

        print()
        print("  심판을 부른다. 문항 수에 비례해 걸린다.")

        # 심판마다 LLM 객체를 따로 준다. ragas 의 LangchainLLMWrapper 는 호출 직전에
        # langchain_llm.n 과 .temperature 를 직접 갈아 끼운다. 셋이 한 객체를 나눠 쓰면
        # 동시에 도는 다른 심판이 n 을 1 로 되돌려 놓는다. ResponseRelevancy 는 n=3 을
        # 요구하는데 1 만 받고 표본 1개로 점수를 낸다 - 조용히 틀린 숫자가 더 나쁘다.
        metrics = [
            Faithfulness(llm=LangchainLLMWrapper(chat_verify.model_copy())),
            ResponseRelevancy(llm=LangchainLLMWrapper(chat_verify.model_copy())),
            LLMContextPrecisionWithoutReference(llm=LangchainLLMWrapper(chat_verify.model_copy())),
        ]

        # ragas 는 자기 추적 트리를 새로 세운다. 우리 부모 run 안에서 돌면 부딪혀 IndexError 가 난다.
        with detached():
            result = evaluate(
                EvaluationDataset(samples=samples),
                metrics=metrics,
                embeddings=LangchainEmbeddingsWrapper(LocalEmbeddings()),
            )

        print()
        print("=" * 74)
        print("2. 심판 점수")
        print("=" * 74)
        for name, score in result._repr_dict.items():
            print(f"  {name:<22} {score:.3f}")
            run.record(**{name: round(float(score), 3)})

        run.record(상품언급=mentioned, 후보밖_언급=invented)

        print()
        print(f"  표본 {len(items)}문항 · 답변 {LLM_MODEL} · 심판 {VERIFY_MODEL} · 임베딩 {EMBED_MODEL} · 근거 {K}개")
        print("  이 숫자를 docs/measurements.md 에 잰 날짜와 함께 옮겨 적는다.")
        print("  점수가 낮으면 1번 표부터 본다. 후보 밖 언급이 0인데 faithfulness 가 낮으면")
        print("  우리 답이 아니라 심판을 의심할 차례다.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
