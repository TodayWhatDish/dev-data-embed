# Last updated: 2026-08-30

"""홀드아웃(is_holdout=1) 리뷰를 질의처럼 넣어, 프로필 필터 + 벡터검색(코사인 유사도)이
원래 구매한 상품을 top-k 안에 다시 찾아내는지 재는 스크립트.

코사인 유사도는 질문-리뷰 한 쌍의 랭킹 점수일 뿐이고, recall@k는 그 랭킹이 홀드아웃
전체에서 몇 번 맞았는지(hits/전체)를 집계한 하류 지표다. 필터를 추가하거나 모델을
바꿀 때 감이 아니라 이 숫자로 비교하려고 만든다 — 절대값 자체보다("70%면 좋은 거야?")
실행 전/후 상대 변화를 보는 용도에 가깝다.

검색 로직 자체는 pipeline/vector_db.py 의 search() 를 그대로 재사용한다.
"""
import time
import json
import random
import sqlite3

from app.features.retrieve import build_where  # 프로필 딕셔너리 -> SQL where절 변환
from app.core.config import DB_PATH, SIZE_CASE, EVAL_DIR, EMBED_MODEL, EMBED_DIM
from pipeline.vector_db import search,connect

def load_product_map(con: sqlite3.Connection)->dict[int,int]:
    """purchase_id -> product_id 사전을 만든다 검색 결과(purchase_id)를 상품으로 해석할 때 쓴다."""
    rows = con.execute('SELECT purchase_id, product_id FROM purchase').fetchall()  # 전체 구매의 (purchase_id, product_id) 쌍을 가져옴
    return dict(rows)  # {purchase_id, product_id}


def load_holdout(con: sqlite3.Connection):
    """색인(chunks / chunk_vectors)에서 빠진, 정답(product_id)을 이미 아는 평가용 표본을 가져온다."""
    return con.execute(f"""
        SELECT
            pu.purchase_id,
            pu.product_id,
            (SELECT ac.name_ko FROM pet AS pe
                JOIN animal_category AS ac ON ac.animal_category_id = pe.animal_category_id
                WHERE pe.pet_id = pu.pet_id) AS animal_category,
            {SIZE_CASE} AS size_category,
            (SELECT al.name_ko FROM pet_allergy AS pa
                JOIN allergen AS al ON al.allergen_id = pa.allergen_id
                WHERE pa.pet_id = pu.pet_id LIMIT 1) AS allergy,
            r.body AS review
        FROM purchase AS pu
        JOIN review AS r ON r.purchase_id = pu.purchase_id
        WHERE r.is_holdout = 1
        AND r.body IS NOT NULL
        AND TRIM(r.body) <> ''
    """).fetchall()

def load_product_names(con: sqlite3.Connection) -> dict[int, str]:
    """product_id -> 상품명 사전. 결과를 사람이 읽을 수 있게 찍을 때 쓴다."""
    rows = con.execute('SELECT product_id, name FROM product').fetchall()
    return dict(rows)

def inspect_misses(con: sqlite3.Connection, runs: list[tuple], n: int = 5) -> None:
    """미스 케이스 n건을 골라, 정답과 실제 상위 결과를 나란히 찍는다."""
    product_of = load_product_map(con)
    name_of = load_product_names(con)

    shown = 0
    for purchase_id, product_id, allergy, review, results in runs:
        ranked_products = [product_of[r_pid] for r_pid, _, _ in results]

        if product_id in ranked_products[:3]:
            continue

        print(f"\n[{purchase_id}] 정답: {name_of[product_id]} (product_id={product_id})")
        print(f"  질의: {review[:60]}")
        rank = ranked_products.index(product_id) + 1 if product_id in ranked_products else None
        print(f"  top50 안 순위: {rank if rank else '없음'}")
        for i, (r_pid, score, doc) in enumerate(results[:3], start=1):
            print(f"  {i}위 [{name_of[product_of[r_pid]]}] 유사도 {score:.3f}")

        shown += 1
        if shown == n:
            break

def is_allergy_contaminated(con: sqlite3.Connection, product_id: int, allergy: str) -> bool:
    """정답 상품에 그 pet의 등록 알레르기 원료가 실제로 들어있는지.

    True면 FILTERS["allergy"](retrieve.py:26-33)가 이 정답을 애초에 후보군에서 뺐다는 뜻 -
    검색 품질과 무관하게 이길 수 없는 홀드아웃 표본이다.
    """
    if not allergy:
        return False
    row = con.execute("""
        SELECT 1 FROM product_ingredient AS pi
        JOIN ingredient_allergen AS ia ON ia.ingredient_id = pi.ingredient_id
        JOIN allergen AS al ON al.allergen_id = ia.allergen_id
        WHERE pi.product_id = ? AND al.name_ko = ?
    """, (product_id, allergy)).fetchone()
    return row is not None

def count_allergy_contamination(con: sqlite3.Connection, runs: list[tuple]) -> None:
    """top50 미스 중 알레르기 필터가 정답 자체를 걸러낸 오염 건수를 센다."""
    product_of = load_product_map(con)
    contaminated = 0
    n_miss = 0
    for purchase_id, product_id, allergy, review, results in runs:
        if any(product_of[r_pid] == product_id for r_pid, _, _ in results):
            continue
        n_miss += 1
        if is_allergy_contaminated(con, product_id, allergy):
            contaminated += 1
    rate = contaminated / n_miss if n_miss else 0.0
    print(f'top50 미스 {n_miss}건 중 알레르기 오염(정답이 필터에 걸림) {contaminated}건 ({rate:.1%})')

def run_holdout_search(con: sqlite3.Connection, top_k_wide: int = 50) -> list[tuple]:
    """홀드아웃 66건을 한 번씩만 검색해서, 이후 지표 계산 함수들이 재사용하게 한다."""
    holdout = load_holdout(con)
    runs = []
    for purchase_id, product_id, animal_category, size, allergy, review in holdout:
        where, params = build_where({'animal_category': animal_category, 'size_category': size, 'allergy': allergy})
        results = search(con, review, where=where, params=params, top_k=top_k_wide)
        runs.append((purchase_id, product_id, allergy, review, results))
    return runs

def rank_of_answer(product_of: dict[int, int], product_id: int, results: list[tuple]) -> int | None:
    """정답 상품이 검색 결과의 몇 번째에 나왔는지(1부터). 없으면 None.

    recall@k도 MRR도 전부 이 정수 하나에서 파생된다 - k마다 결과를 다시 훑을 이유가 없다.
    """
    for position, (r_pid, _, _) in enumerate(results, start=1):
        if product_of[r_pid] == product_id:
            return position
    return None


def score_runs(con: sqlite3.Connection, runs: list[tuple]) -> list[dict]:
    """검색 결과를 표본별 한 줄 기록으로 압축한다. 모델 비교는 이 기록끼리 한다."""
    product_of = load_product_map(con)
    return [
        {'purchase_id': purchase_id,
         'product_id': product_id,
         'rank': rank_of_answer(product_of, product_id, results)}
        for purchase_id, product_id, allergy, review, results in runs
    ]


def summarize(records: list[dict], ks: tuple = (1, 3, 10)) -> dict:
    """기록에서 지표를 뽑는다.

    recall@k 하나만 보면 k 경계에서 우연히 갈린 표본에 결론이 휘둘린다.
    MRR 은 순위를 통째로 반영해서(1위=1.0, 5위=0.2) 그 흔들림이 덜하다.
    """
    ranks = [record['rank'] for record in records]
    n = len(ranks)
    metrics = {f'recall@{k}': sum(1 for r in ranks if r is not None and r <= k) / n for k in ks}
    metrics['mrr'] = sum(1 / r for r in ranks if r is not None) / n
    metrics['n'] = n
    return metrics


def noise_band(records: list[dict], k: int = 3, trials: int = 2000, seed: int = 0) -> tuple:
    """같은 표본을 복원추출로 다시 뽑았을 때 recall@k 가 흔들리는 폭(95%).

    표본이 66건뿐이라 1건 = 1.5%p 다. 이 폭 안의 모델 간 차이는 '차이'가 아니라
    어느 리뷰가 홀드아웃으로 뽑혔느냐의 운이다. 모델을 고르기 전에 이 폭부터 안다.
    """
    hits = [1 if (r['rank'] is not None and r['rank'] <= k) else 0 for r in records]
    n = len(hits)
    rng = random.Random(seed)
    rates = sorted(sum(rng.choice(hits) for _ in range(n)) / n for _ in range(trials))
    return rates[int(trials * 0.025)], rates[int(trials * 0.975)]

def measure_query_latency(n: int = 30) -> float:
    """질의 1건을 벡터로 만드는 평균 시간(ms).

    색인은 배포 때 한 번이지만 질의 인코딩은 요청마다 일어난다 - 사용자가 체감하는
    비용은 이쪽이고, 품질이 노이즈 안에서 뭉칠 때 결정을 가르는 축이 된다.
    """
    from app.core.embedder import embed_query
    embed_query('워밍업')  # 첫 호출엔 모델 로딩이 섞여서 지표로 못 쓴다
    start = time.perf_counter()
    for i in range(n):
        embed_query(f'피부가 예민한 아이에게 줄 사료를 찾고 있어요 {i}')
    return (time.perf_counter() - start) / n * 1000

def save_run(records: list[dict], metrics: dict) -> None:
    """모델 이름으로 결과 파일을 남긴다.

    모델을 바꿔 재색인하면 chunk_vectors 가 DROP 되므로(vector_db.py:38) 이전 모델의
    결과는 DB 에 남지 않는다. 비교하려면 DB 밖에 이렇게 남겨두는 수밖에 없다.
    """
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EVAL_DIR / f"{EMBED_MODEL.replace('/', '__')}.json"
    path.write_text(
        json.dumps({'model': EMBED_MODEL, 'dim': EMBED_DIM,
                    'metrics': metrics, 'records': records},
                   ensure_ascii=False, indent=2),
        encoding='utf-8')
    print(f'결과 저장: {path}')

if __name__ == '__main__':
    con = connect()
    runs = run_holdout_search(con)
    records = score_runs(con, runs)
    metrics = summarize(records)
    metrics['query_ms'] = measure_query_latency()

    print(f'모델: {EMBED_MODEL} ({EMBED_DIM}차원)')
    for name, value in metrics.items():
        print(f'  {name:<12} {value:.3f}' if isinstance(value, float) else f'  {name:<12} {value}')

    low, high = noise_band(records, k=3)
    print(f'  recall@3 95% 구간 {low:.1%} ~ {high:.1%} - 이 폭 안의 차이는 무시한다')

    save_run(records, metrics)
    count_allergy_contamination(con, runs)
    inspect_misses(con, runs)
    con.close()
