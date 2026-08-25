# Last updated: 2026-08-25
'''홀드아웃(is_holdout=1) 리뷰를 질의처럼 넣어, 프로필 필터+벡터검색이
원래 구매한 상품을 다시 찾아내는지(recall@k)를 재는 평가 스크립트.

필터를 추가하거나 모델을 바꿀 때 감이 아니라 이 숫자로 좋아졌는지 비교하려고 만든다.
절대값 자체보다("70%면 좋은 거야?") 실행 전/후 상대 변화를 보는 용도에 가깝다.
'''

import sqlite3

from app.features.retrieve import build_where, VectorStore  # 프로필 딕셔너리 -> SQL where절 변환
from app.core.config import DB_PATH  # DB 경로
from app.core.embedder import get_embeddings
from sentence_transformers import SentenceTransformer


def load_product_map(con: sqlite3.Connection)->dict[int,int]:
    """purchase_id -> product_id 사전을 만든다 검색 결과(purchase_id)를 상품으로 해석할 때 쓴다."""
    rows = con.execute('SELECT purchase_id, product_id FROM pet_purchases').fetchall()  # 전체 구매의 (purchase_id, product_id) 쌍을 가져옴
    return dict(rows)  # {purchase_id, product_id}


def load_holdout(con: sqlite3.Connection):
    # review_vectors에 빠진, 정답(product_id)을 이미 아는 평가용 표본을 가져온다
    return con.execute("""
    SELECT purchase_id, product_id, size_category, allergy, review
    FROM pet_purchases
    WHERE is_holdout = 1
    AND review IS NOT NULL
    AND TRIM(review) <> ''
    """).fetchall()  # 원본 테이블에서 is_holdout=1(색인에서 빠진 것)이고 리뷰가 있는 행만


def evaluate(con : sqlite3.Connection, model:SentenceTransformer, k:int=3)->float:
    """홀드아웃 리뷰 하나하나를 질의로 넣어 recall@k를 잰다.
    VectorStore는 생성 비용(모델 로딩 + 벡터로딩)이 크므로 루프 밖에서 한 번만 만들고, 404건의 질의는 그 인스턴스를 재사용한다."""
    store = VectorStore(con,model)
    product_of = load_product_map(con)  # 검색 결과(purchase_id) 상품 번호 사전
    holdout = load_holdout(con)         # 채점할 문제 (구매 건, 정답 상품)

    if not holdout:
        raise SystemExit(
            'is_holdout=1인 리뷰가 없습니다.'
        )

    hits = 0
    for purchase_id, product_id, size, allergy, review in holdout:
        where, params = build_where({'size_category':size, 'allergy': allergy})
        results = store.search(review, where=where, params=params, top_k=k)
        if any(product_of[r_pid] == product_id for r_pid, _, _ in results):
            hits+=1

    rate = hits/len(holdout)
    print(f'recall@{k} : {hits}/{len(holdout)} = {rate:.1%}')
    return rate


if __name__ == '__main__':
    con = sqlite3.connect(DB_PATH)  # DB 연결
    model = get_embeddings()  # 문장을 벡터로 바꿀 모델 로드
    evaluate(con, model)  # 평가 실행 -> recall@3 출력
    con.close()  # 연결 정리
