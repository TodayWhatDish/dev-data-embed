# Last updated: 2026-08-30

"""홀드아웃(is_holdout=1) 리뷰를 질의처럼 넣어, 프로필 필터 + 벡터검색(코사인 유사도)이
원래 구매한 상품을 top-k 안에 다시 찾아내는지 재는 스크립트.

코사인 유사도는 질문-리뷰 한 쌍의 랭킹 점수일 뿐이고, recall@k는 그 랭킹이 홀드아웃
전체에서 몇 번 맞았는지(hits/전체)를 집계한 하류 지표다. 필터를 추가하거나 모델을
바꿀 때 감이 아니라 이 숫자로 비교하려고 만든다 — 절대값 자체보다("70%면 좋은 거야?")
실행 전/후 상대 변화를 보는 용도에 가깝다.

검색 로직 자체는 pipeline/vector_db.py 의 search() 를 그대로 재사용한다.
"""

import sqlite3

from app.features.retrieve import build_where  # 프로필 딕셔너리 -> SQL where절 변환
from app.core.config import DB_PATH, SIZE_CASE  
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

def inspect_misses(con: sqlite3.Connection, n: int = 5, top_k_wide: int = 50) -> None:
    """미스 케이스 n건을 골라, 정답과 실제 상위 결과를 나란히 찍는다."""
    product_of = load_product_map(con)
    name_of = load_product_names(con)
    holdout = load_holdout(con)

    shown = 0
    for purchase_id, product_id, animal_category, size, allergy, review in holdout:
        where, params = build_where({'animal_category': animal_category, 'size_category': size, 'allergy': allergy})
        results = search(con, review, where=where, params=params, top_k=top_k_wide)
        ranked_products = [product_of[r_pid] for r_pid, _, _ in results]

        if product_id in ranked_products[:3]:
            continue  # top-3 hit은 건너뛰고 미스만 본다

        print(f"\n[{purchase_id}] 정답: {name_of[product_id]} (product_id={product_id})")
        print(f"  질의: {review[:60]}")
        rank = ranked_products.index(product_id) + 1 if product_id in ranked_products else None
        print(f"  top50 안 순위: {rank if rank else '없음'}")
        for i, (r_pid, score, doc) in enumerate(results[:3], start=1):
            print(f"  {i}위 [{name_of[product_of[r_pid]]}] 유사도 {score:.3f}")

        shown += 1
        if shown == n:
            break
                                                               
def evaluate(con : sqlite3.Connection, k:int=3)->float:
    """홀드아웃 리뷰 하나하나를 질의로 넣어 recall@k를 잰다."""
    product_of = load_product_map(con)  # 검색 결과(purchase_id) 상품 번호 사전
    holdout = load_holdout(con)         # 채점할 문제 (구매 건, 정답 상품)

    if not holdout:
        raise SystemExit(
            'is_holdout=1인 리뷰가 없습니다.'
        )

    hits = 0
    for purchase_id, product_id, animal_category, size, allergy, review in holdout:
        where, params = build_where({'animal_category':animal_category, 'size_category':size, 'allergy': allergy})
        results = search(con, review, where=where, params=params, top_k=k)
        if any(product_of[r_pid] == product_id for r_pid, _, _ in results):
            hits+=1

    rate = hits/len(holdout)
    print(f'recall@{k} : {hits}/{len(holdout)} = {rate:.1%}')
    return rate

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

def count_allergy_contamination(con: sqlite3.Connection, top_k_wide: int = 50) -> None:
    """top50 미스 중 알레르기 필터가 정답 자체를 걸러낸 오염 건수를 센다."""
    product_of = load_product_map(con)
    holdout = load_holdout(con)

    contaminated = 0
    n_miss = 0
    for purchase_id, product_id, animal_category, size, allergy, review in holdout:
        where, params = build_where({'animal_category': animal_category, 'size_category': size, 'allergy': allergy})
        results = search(con, review, where=where, params=params, top_k=top_k_wide)
        if any(product_of[r_pid] == product_id for r_pid, _, _ in results):
            continue  # 적중은 오염 여부를 셀 필요 없음

        n_miss += 1
        if is_allergy_contaminated(con, product_id, allergy):
            contaminated += 1

    rate = contaminated / n_miss if n_miss else 0.0
    print(f'top50 미스 {n_miss}건 중 알레르기 오염(정답이 필터에 걸림) {contaminated}건 ({rate:.1%})')

if __name__ == '__main__':
    con = connect()
    evaluate(con)  # 평가 실행 -> recall@3 출력
    count_allergy_contamination(con)  # top50 미스 중 알레르기 오염 비율 확인
    inspect_misses(con)
    con.close()
