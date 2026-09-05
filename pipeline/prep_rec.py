# Last Updated : 2026-08-30

"""5단계 검증에 필요한 데이터를 만든다: holdout 지정 + product_vectors + customer_vectors."""

import sqlite3
from collections import defaultdict
import sys

import numpy as np
import sqlite_vec

from app.core.config import DB_PATH
from app.core.embedder import embed_documents
from app.domain.embedding_text import product_text


def mark_holdout(con: sqlite3.Connection):
    """고객별 최근 구매(리뷰 있는 것 중) 1건을 홀드아웃으로 표시한다."""
    con.execute("UPDATE review SET is_holdout = 0")
    con.execute("""
        UPDATE review SET is_holdout = 1
        WHERE purchase_id IN (
            SELECT purchase_id FROM (
                SELECT r.purchase_id, ROW_NUMBER() OVER (
                    PARTITION BY pe.user_id ORDER BY pu.purchased_at DESC, pu.purchase_id DESC
                ) AS rn
                FROM review AS r
                JOIN purchase AS pu ON pu.purchase_id = r.purchase_id
                JOIN pet AS pe ON pe.pet_id = pu.pet_id
                WHERE TRIM(r.body) <> ''
            ) WHERE rn = 1
        )
    """)
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM review WHERE is_holdout = 1").fetchone()[0]
    print(f"[holdout] 고객 {n}명의 최근 구매를 홀드아웃으로 표시")


def build_product_vectors(con: sqlite3.Connection):
    """product를 문장으로 임베딩해 product_vectors에 저장한다."""
    cur = con.execute("""
        SELECT
            p.product_id,
            p.brand, p.name AS product_name,
            pc_parent.name_ko AS category, pc.name_ko AS sub_category,
            GROUP_CONCAT(DISTINCT fp.name_ko) AS target_feeding_purpose,
            p.food_form AS target_food_form,
            GROUP_CONCAT(DISTINCT ing.name_ko) AS ingredients,
            NULL AS tags,
            p.description
        FROM product AS p
        LEFT JOIN product_category AS pc ON pc.product_category_id = p.product_category_id
        LEFT JOIN product_category AS pc_parent ON pc_parent.product_category_id = pc.parent_id
        LEFT JOIN product_feeding_purpose AS pfp ON pfp.product_id = p.product_id
        LEFT JOIN feeding_purpose AS fp ON fp.feeding_purpose_id = pfp.feeding_purpose_id
        LEFT JOIN product_ingredient AS pi ON pi.product_id = p.product_id
        LEFT JOIN ingredient AS ing ON ing.ingredient_id = pi.ingredient_id
        GROUP BY p.product_id
    """)
    cols = [d[0] for d in cur.description]
    products = [dict(zip(cols, row)) for row in cur.fetchall()]
    vectors = embed_documents([product_text(p) for p in products])

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
        SELECT pe.user_id, v.vector
        FROM purchase AS p
        JOIN pet AS pe ON pe.pet_id = p.pet_id
        JOIN review AS r ON r.purchase_id = p.purchase_id
        JOIN chunk_vectors AS v ON v.purchase_id = p.purchase_id
        WHERE r.is_holdout = 0
    """).fetchall()

    buckets = defaultdict(list)
    for user_id, vec in rows:
        buckets[user_id].append(np.frombuffer(vec, dtype=np.float32))

    con.execute("DROP TABLE IF EXISTS customer_vectors")
    con.execute("CREATE TABLE customer_vectors (customer_id INTEGER PRIMARY KEY, vector BLOB)")
    for user_id, vecs in buckets.items():
        mean_vec = np.mean(vecs, axis=0).astype(np.float32)
        mean_vec /= np.linalg.norm(mean_vec) + 1e-9
        con.execute(
            "INSERT INTO customer_vectors VALUES (?, ?)",
            (user_id, sqlite_vec.serialize_float32(mean_vec)),
        )
    con.commit()
    print(f"[customer_vectors] 고객 {len(buckets)}명 벡터 저장")


def main():
    """홀드아웃 표시와 벡터 빌드 사이에는 chunk.py -> embed.py 가 끼어야 한다.

    mark_holdout 이 색인 대상(INDEX_FILTER 의 is_holdout=0)을 바꾸고,
    build_customer_vectors 는 그 색인 결과인 chunk_vectors 를 읽기 때문이다.
    한 번에 돌리면 낡은 벡터로 고객 벡터를 만든다.

        python -m pipeline.prep_rec holdout
        python -m pipeline.chunk
        python -m pipeline.embed
        python -m pipeline.prep_rec vectors
    """
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    con = sqlite3.connect(DB_PATH)
    if step in ("holdout", "all"):
        mark_holdout(con)
    if step in ("vectors", "all"):
        build_product_vectors(con)
        build_customer_vectors(con)
    con.close()


if __name__ == "__main__":
    main()
