# Last updated: 2026-08-17
'''홀드아웃(is_holdout=1) 리뷰를 질의처럼 넣어, 프로필 필터+벡터검색이
원래 구매한 상품을 다시 찾아내는지(recall@k)를 재는 평가 스크립트.

필터를 추가하거나 모델을 바꿀 때 감이 아니라 이 숫자로 좋아졌는지 비교하려고 만든다.
절대값 자체보다("70%면 좋은 거야?") 실행 전/후 상대 변화를 보는 용도에 가깝다.
'''

import sqlite3

from app.features.retrieve import build_where, VectorStore  # 프로필 딕셔너리 -> SQL where절 변환

from sentence_transformers import SentenceTransformer  # 문장을 벡터로 바꿔주는 모델 클래스
from app.core.config import DB_PATH, EMBED_MODEL  # DB 경로, 임베딩 모델 이름


def load_product_map(con):
    # purchase_id -> product_id 사전. 검색 결과를 상품으로 해석할 때 씀
    rows = con.execute('SELECT purchase_id, product_id FROM pet_purchases').fetchall()  # 전체 구매의 (purchase_id, product_id) 쌍을 가져옴
    return dict(rows)  # {purchase_id, product_id}


def load_holdout(con):
    # review_vectors에 빠진, 정답(product_id)을 이미 아는 평가용 표본을 가져온다
    return con.execute("""
    SELECT purchase_id, product_id, size_category, allergy, review
    FROM pet_purchases
    WHERE is_holdout = 1
    AND review IS NOT NULL
    AND TRIM(review) <> ''
    """).fetchall()  # 원본 테이블에서 is_holdout=1(색인에서 빠진 것)이고 리뷰가 있는 행만


def evaluate(con, model, k=3):
    product_of = load_product_map(con)  # 검색 결과(purchase_id)를 상품 번호로 바꿔줄 사전
    holdout = load_holdout(con)  # 채점할 문제 404개

    hits = 0  # 맞힌 개수, 0점에서 시작

    for purchase_id, product_id, size, allergy, review in holdout:  # 문제를 하나씩 꺼냄. product_id가 이 문제의 정답
        where, params = build_where({'size_category': size, 'allergy': allergy})  # 이 손님 프로필로 SQL 조건 생성
        results = VectorStore.search(con, model, review, where=where, params=params, top_k=k)  # 리뷰를 질의로 검색 -> top-k (구매 번호,유사도 점수, 리뷰 문장)
        # r_pid : 어떤 리뷰(구매 건)가 검색됐는지, top-k 중 하나라도 정답 상품과 같으면 
        if any(product_of[r_pid] == product_id for r_pid, _, _ in results):  # 
            hits += 1  # 맞힌 걸로 채점

    rate = hits / len(holdout)  # 정답률 = 맞힌 개수 / 전체 문제 수
    print(f'recall@{k} : {hits}/{len(holdout)} = {rate:.1%} ({hits}/{len(holdout)})')
    return rate


if __name__ == '__main__':
    con = sqlite3.connect(DB_PATH)  # DB 연결
    model = SentenceTransformer(EMBED_MODEL)  # 문장을 벡터로 바꿀 모델 로드
    evaluate(con, model)  # 평가 실행 -> recall@3 출력
    con.close()  # 연결 정리
