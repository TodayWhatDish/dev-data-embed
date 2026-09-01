# Last Updated : 2026-09-01

"""두 모델의 평가 결과(data/eval/*.json)를 표본별로 짝지어 비교한다.

총점만 보면 표본 몇 건 차이가 그대로 결론이 된다. 두 모델이 똑같은 질의를 풀었으므로
표본을 짝지어 "누가 어디서 이겼는지"를 세면 총점보다 훨씬 예민하게 차이를 볼 수 있다.

    python -m pipeline.eval.compare intfloat/multilingual-e5-small BAAI/bge-m3
"""

import json
import sys

from app.core.config import EVAL_DIR

# 순위가 top50 밖(None)인 표본을 비교할 때 쓰는 대체값. 실제 순위가 아니라 "맨 뒤" 표시다.
OUT_OF_RANGE = 999


def load(model: str) -> dict:
    path = EVAL_DIR / f"{model.replace('/', '__')}.json"
    if not path.exists():
        raise SystemExit(f"결과 파일이 없습니다: {path}\n"
                         f"EMBED_MODEL={model} 로 재색인 후 eval.py 를 돌리세요.")
    return json.loads(path.read_text(encoding='utf-8'))


def compare(model_a: str, model_b: str, k: int = 3) -> None:
    a, b = load(model_a), load(model_b)
    rank_a = {r['purchase_id']: r['rank'] for r in a['records']}
    rank_b = {r['purchase_id']: r['rank'] for r in b['records']}

    shared = sorted(set(rank_a) & set(rank_b))
    if len(shared) != len(rank_a) or len(shared) != len(rank_b):
        print(f"경고: 표본이 다르다 (A {len(rank_a)}건 / B {len(rank_b)}건 / 공통 {len(shared)}건). "
              "홀드아웃을 바꾼 뒤 한쪽만 재측정한 상태다 - 비교가 성립하지 않는다.")

    def hit(rank):
        return rank is not None and rank <= k

    only_a = [pid for pid in shared if hit(rank_a[pid]) and not hit(rank_b[pid])]
    only_b = [pid for pid in shared if hit(rank_b[pid]) and not hit(rank_a[pid])]
    flips = len(only_a) + len(only_b)

    print(f"A = {model_a} ({a['dim']}차원) mrr {a['metrics']['mrr']:.3f}")
    print(f"B = {model_b} ({b['dim']}차원) mrr {b['metrics']['mrr']:.3f}")
    print(f"\n@{k} 뒤집힘: A만 맞춘 것 {len(only_a)}건 / B만 맞춘 것 {len(only_b)}건 (총 {flips}건)")

    # 부호검정: 뒤집힘이 6건일 때 6:0 이어야 겨우 p<0.05 다.
    # 6건 미만이면 어떻게 갈리든 우연과 구별할 수 없다.
    if flips < 6:
        print("  -> 뒤집힘이 너무 적다. 우열을 말할 수 없으니 비용 축(차원/속도)에서 고른다.")
    else:
        winner = 'B' if len(only_b) > len(only_a) else 'A'
        print(f"  -> {winner} 우세 {abs(len(only_b) - len(only_a))}건. 한쪽으로 쏠릴수록 실재하는 차이다.")

    # recall 경계에 안 걸린 개선/악화까지 본다 - 43위가 39위로 올라온 것도 신호다.
    moved = [(rank_a[pid] or OUT_OF_RANGE) - (rank_b[pid] or OUT_OF_RANGE) for pid in shared]
    better = sum(1 for d in moved if d > 0)
    worse = sum(1 for d in moved if d < 0)
    print(f"순위 이동: B가 올린 표본 {better}건 / 내린 표본 {worse}건 / 동일 {len(shared) - better - worse}건")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    compare(sys.argv[1], sys.argv[2])