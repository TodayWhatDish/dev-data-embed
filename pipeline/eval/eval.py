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

def evaluate(con : sqlite3.Connection, k:int=3)->float:
    """홀드아웃 리뷰 하나하나를 질의로 넣어 recall@k를 잰다."""
    product_of = load_product_map(con)  # 검색 결과(purchase_id) 상품 번호 사전
    holdout = load_holdout(con)         # 채점할 문제 (구매 건, 정답 상품)

    if not holdout:
        raise SystemExit(
            'is_holdout=1인 리뷰가 없습니다.'
        )

    hits = 0
    for purchase_id, product_id, size, allergy, review in holdout:
        where, params = build_where({'size_category':size, 'allergy': allergy})
        results = search(con, review, where=where, params=params, top_k=k)
        if any(product_of[r_pid] == product_id for r_pid, _, _ in results):
            hits+=1

    rate = hits/len(holdout)
    print(f'recall@{k} : {hits}/{len(holdout)} = {rate:.1%}')
    return rate


def has_ingredient_slot(con: sqlite3.Connection, prouct_id: int, review: str) -> bool:
    """리뷰 본문에 그 상품의 원료(재료)명이 하나라도 등장하는지."""
    names = con.execute("""
        SELECT i.name_ko
        FROM product_ingredient AS pi
        JOIN ingredient AS i ON i.ingredient_id = pi.ingredient_id
        WHERE pi.product_id = ?
    """, (prouct_id,)).fetchall()
    return any(name in review for (name,) in names)

def diagnose_top50_miss(con: sqlite3.Connection, top_k_wide: int=50) -> None:
    """top50 미스가 '원료 슬롯 없음'에 쏠려있는지 확인한다"""
    product_of = load_product_map(con)
    holdout = load_holdout(con)

    top50_miss, top50_hit =[],[]
    for purchase_id, product_id, size, allergy, review in holdout:
        where, params = build_where({'size_category':size, 'allergy':allergy})
        results = search(con,review,where=where,params=params,top_k=top_k_wide)
        slot = has_ingredient_slot(con,product_id,review)
        bucket = top50_hit if any(product_of[r_pid] == product_id for r_pid, _, _ in results) else top50_miss
        bucket.append(slot)

    def slot_rate(bucket: list[bool]) -> float:
        return sum(bucket) / len(bucket) if bucket else 0.0

    print(f'top50 미스 {len(top50_miss)}건 중 원료 슬롯 있음 비율: {slot_rate(top50_miss):.1%}')
    print(f'top50 적중 {len(top50_hit)}건 중 원료 슬롯 있음 비율: {slot_rate(top50_hit):.1%}')

if __name__ == '__main__':
    con = connect()
    evaluate(con)  # 평가 실행 -> recall@3 출력
    diagnose_top50_miss(con) # top50 미스 vs 원료 슬롯 상관관계 확인
    con.close()  
