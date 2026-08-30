# Last Updated : 2026-08-30

"""5단계 검증에 필요한 데이터를 만든다: holdout 지정 + product_vectors + customer_vectors."""

import sqlite3
from collections import defaultdict

import numpy as np
import sqlite_vec

from app.core.config import DB_PATH
from app.core.embedder import get_embeddings
from app.domain.embedding_text import product_text


def mark_holdout(con: sqlite3.Connection):
    """고객별 최근 구매(리뷰 있는 것 중) 1건을 홀드아웃으로 표시한다."""
    con.execute("UPDATE pet_purchases SET is_holdout = 0")
    con.execute("""
        UPDATE pet_purchases SET is_holdout = 1
        WHERE purchase_id IN (
            SELECT purchase_id FROM (
                SELECT purchase_id, ROW_NUMBER() OVER (
                    PARTITION BY customer_id ORDER BY purchased_at DESC, purchase_id DESC
                ) AS rn
                FROM pet_purchases
                WHERE review IS NOT NULL AND TRIM(review) <> ''
            ) WHERE rn = 1
        )
    """)
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM pet_purchases WHERE is_holdout = 1").fetchone()[0]
    print(f"[holdout] 고객 {n}명의 최근 구매를 홀드아웃으로 표시")


def build_product_vectors(con: sqlite3.Connection):
    """pet_products를 문장으로 임베딩해 product_vectors에 저장한다."""
    model = get_embeddings()
    cur = con.execute("SELECT * FROM pet_products")
    cols = [d[0] for d in cur.description]
    products = [dict(zip(cols, row)) for row in cur.fetchall()]
    vectors = model.encode(
        [product_text(p) for p in products], normalize_embeddings=True, show_progress_bar=False
    )

    con.execute("DROP TABLE IF EXISTS product_vectors")
    con.execute("CREATE TABLE product_vectors (product_id INTEGER PRIMARY KEY, vector BLOB)")
    con.executemany(
        "INSERT INTO product_vectors VALUES (?, ?)",
        [(p["product_id"], sqlite_vec.serialize_float32(v)) for p, v in zip(products, vectors)],
    )
    con.commit()
    print(f"[product_vectors] 상품 {len(products)}개 벡터 저장")


def build_customer_vectors(con: sqlite3.Connection):
    """고객 벡터 = 홀드아웃을 뺀 그 고객 리뷰 조각 벡터의 평균 (정답을 미리 보지 않도록)."""
    rows = con.execute("""
        SELECT p.customer_id, v.vector FROM pet_purchases AS p
        JOIN chunk_vectors AS v ON v.purchase_id = p.purchase_id
        WHERE p.is_holdout = 0
    """).fetchall()

    buckets = defaultdict(list)
    for customer_id, vec in rows:
        buckets[customer_id].append(np.frombuffer(vec, dtype=np.float32))

    con.execute("DROP TABLE IF EXISTS customer_vectors")
    con.execute("CREATE TABLE customer_vectors (customer_id INTEGER PRIMARY KEY, vector BLOB)")
    for customer_id, vecs in buckets.items():
        mean_vec = np.mean(vecs, axis=0).astype(np.float32)
        mean_vec /= np.linalg.norm(mean_vec) + 1e-9
        con.execute(
            "INSERT INTO customer_vectors VALUES (?, ?)",
            (customer_id, sqlite_vec.serialize_float32(mean_vec)),
        )
    con.commit()
    print(f"[customer_vectors] 고객 {len(buckets)}명 벡터 저장")


def main():
    con = sqlite3.connect(DB_PATH)
    mark_holdout(con)
    build_product_vectors(con)
    build_customer_vectors(con)  # mark_holdout 다음이어야 함
    con.close()


if __name__ == "__main__":
    main()
