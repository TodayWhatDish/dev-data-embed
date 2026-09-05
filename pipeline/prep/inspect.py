"""질문 하나를 벡터로 바꿔 실제 검색 결과를 눈으로 확인한다. (6단계, 육안 확인용)

검사(check_*)와 다르다 - 참/거짓을 판정하지 않고, 결과를 그냥 보여주기만 한다.

참고파일은 chunk/product/customer/review 네 벌을 다 훑지만, 우리는
review_vectors가 없다(리뷰는 chunk 단위로만 쪼개서 저장한다) - 그래서 세 벌만 본다.
"""

import sqlite3
import time

import sqlite_vec

from app.core.embedder import embed_query

_TABLE = {
    "chunk": "chunk_vectors",
    "product": "product_vectors",
    "customer": "customer_vectors",
}


def _rows_for(con: sqlite3.Connection, kind: str, q_vec) -> list[tuple]:
    if kind == "chunk":
        return con.execute("""
            SELECT v.purchase_id, c.body, vec_distance_cosine(v.vector, ?) AS distance
            FROM chunk_vectors AS v
            JOIN chunks AS c ON c.purchase_id = v.purchase_id AND c.chunk_index = v.chunk_index
            ORDER BY distance
        """, (q_vec,)).fetchall()

    if kind == "product":
        return con.execute("""
            SELECT v.product_id, p.brand || ' ' || p.name AS body,
                   vec_distance_cosine(v.vector, ?) AS distance
            FROM product_vectors AS v
            JOIN product AS p ON p.product_id = v.product_id
            ORDER BY distance
        """, (q_vec,)).fetchall()

    if kind == "customer":
        # customer_vectors는 그 고객 리뷰들의 평균이라 원문 자체가 없다.
        return con.execute("""
            SELECT customer_id, '(집계 벡터 - 원문 없음)' AS body,
                   vec_distance_cosine(vector, ?) AS distance
            FROM customer_vectors
            ORDER BY distance
        """, (q_vec,)).fetchall()

    raise ValueError(f"모르는 kind: {kind}")


def inspect(con: sqlite3.Connection, kind: str, questions: list[str], top_k: int = 3) -> None:
    """질문마다 kind 벡터 테이블에서 코사인 거리로 top_k개를 찾아 화면에 찍는다."""
    table = _TABLE.get(kind)
    if table is None:
        print(f"[6단계] 모르는 kind '{kind}' 라 건너뜁니다.")
        return

    exists = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        print(f"[6단계] {table} 테이블이 없어 '{kind}' 검색을 건너뜁니다.")
        return

    try:
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
    except sqlite3.OperationalError:
        pass  # 커넥션에 이미 로드돼 있으면 여기서 에러가 나므로 무시한다.

    for question in questions:
        started = time.time()
        # 실제 검색(vector_db.search)과 같은 embed_query를 쓴다 - 여기만 접두사를 빼면
        # e5 계열에서 이 화면과 진짜 검색 결과가 달라져서, 눈으로 확인하는 의미가 없어진다.
        q_vec = sqlite_vec.serialize_float32(embed_query(question))
        rows = _rows_for(con, kind, q_vec)[: top_k * 5]

        best = {}
        for row_id, body, distance in rows:
            if row_id not in best or distance < best[row_id][1]:
                best[row_id] = (body, distance)
        ranked = sorted(best.items(), key=lambda item: item[1][1])[:top_k]

        elapsed = time.time() - started
        print(f"\n[6단계-{kind}] 질문: {question}  ({elapsed:.2f}초)")
        for row_id, (body, distance) in ranked:
            print(f"  [{1 - distance:.3f}] id={row_id} :: {str(body)[:60]}")
