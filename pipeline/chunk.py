# Last Updated : 2026-08-24

"""리뷰를 임베딩용 문서로 조립하고 토큰 한도에 맞게 자른다. 벡터는 안 만든다 - build_index.py가 한다.

자르는 건 몇 초, 임베딩은 모델 로딩 포함 수십 초 - 값이 다른 작업이라 나눴다.
"""

import sqlite3
import statistics
import sys
from pathlib import Path

from transformers import logging as hf_logging

# 터미널에 출력할 수 없는 특수 이모지나 기호 등을 대체문자로 변경하여 오류를 방지
sys.stdout.reconfigure(errors="replace")

# 청킹하는 문자가 최대 토큰수를 넘어설 때 지저분하게 발생하는 에러 권고사항을 꺼줌.
# 중요한 에러 문구는 그대로 출력 처리
hf_logging.set_verbosity_error()

from app.core.config import DB_PATH, EMBED_MAX_TOKENS, INDEX_FILTER
from pipeline.prep import chunking, embedding, storage


def fetch_rows(cur: sqlite3.Cursor):
    """자를 대상 리뷰를 상품 정보와 함께 읽어온다. (대상 조건인 INDEX_FILTER는 config.py에 명시)"""
    # 컬럼 이름으로 꺼내야 build_doc 이 row['breed'] 처럼 읽을 수 있다.
    cur.row_factory = sqlite3.Row
    return cur.execute(f"""
        SELECT
            p.purchase_id, p.category, p.breed, p.size_category, p.age_group,
            p.allergy, p.health_condition, p.rating, p.review,
            pr.sub_category, pr.product_name,
            pr.target_feeding_purpose, pr.target_food_form
        FROM pet_purchases AS p
        JOIN pet_products AS pr ON pr.product_id = p.product_id
        WHERE {INDEX_FILTER}
        ORDER BY p.purchase_id
    """).fetchall()


def main():
    con = sqlite3.connect(DB_PATH)
    rows = fetch_rows(con.cursor())
    if not rows:
        raise SystemExit("자를 리뷰가 없습니다. 먼저 load_db.py 를 실행하세요.")

    # (purchase_id, 문서) 쌍으로 넘긴다. 한 리뷰가 조각 여러 개로 쪼개져도
    # 그 조각이 원래 어느 리뷰에서 나왔는지 따라붙어야 하기 때문이다.
    docs = [(row["purchase_id"], embedding.build_review_doc(row)) for row in rows]
    chunks = chunking.split_reviews(docs)
    storage.save_chunks(con, chunks)

    # 자른 결과가 멀쩡한지는 눈으로 봐야 안다. 토큰 분포를 요약해 남긴다.
    tokens = [chunk["n_tokens"] for chunk in chunks]
    print(f"\n리뷰 {len(rows)}건 -> 조각 {len(chunks)}개 (쪼개지며 늘어난 조각 {len(chunks) - len(rows)}개)")
    print(f"토큰 평균 {statistics.mean(tokens):.1f} / 중앙값 {statistics.median(tokens):.0f} / 최대 {max(tokens)}")

    # CHUNK_SIZE 안으로 잘랐으니 여기 걸리면 안 된다. 걸린다면 자르기가 제 몫을 못 한 것이고,
    # 그대로 두면 임베딩 때 뒤가 조용히 잘려나간다.
    over = sum(1 for n in tokens if n > EMBED_MAX_TOKENS)
    if over:
        print(
            f"주의: 모델 한도({EMBED_MAX_TOKENS} 토큰)를 넘는 조각 {over}개 - 뒤가 잘려 누락된다"
        )

    print("벡터는 여기서 만들지 않는다. 이어서 embed_reviews.py 를 실행하세요.")
    con.close()


if __name__ == "__main__":
    main()
