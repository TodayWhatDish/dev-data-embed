"""질문 하나를 벡터로 바꿔 실제 검색 결과를 눈으로 확인한다. (6단계, 육안 확인용)

검사(check_*)와 다르다 - 참/거짓을 판정하지 않고, 결과를 그냥 보여주기만 한다.

참고파일은 chunk/product/customer/review 네 벌을 다 훑지만, 우리는
review_vectors가 없다(리뷰는 chunk 단위로만 쪼개서 저장한다) - 그래서 세 벌만 본다.

거리는 pgvector 의 cosine_distance(`<=>`)로 잰다 - 예전 sqlite-vec 의 vec_distance_cosine()과 값이 같다.
"""

import time

from sqlalchemy import Connection, Select, and_, literal, select
from sqlalchemy import inspect as sa_inspect

from app.core.embedder import embed_query
from app.models.chunk import Chunk, ChunkVector, CustomerVector, ProductVector
from app.models.product import Product

_TABLE = {
    "chunk": "chunk_vectors",
    "product": "product_vectors",
    "customer": "customer_vectors",
}


def _stmt_for(kind: str, q_vec: list[float]) -> Select:
    """
    # Summary
    * (id, 본문, 거리) 세 컬럼을 고르는 쿼리. 정렬·LIMIT 은 부르는 쪽이 붙인다
    # params
    * kind: chunk / product / customer
    * q_vec: 질문 벡터
    # examples
    * ('product', 질문벡터) -> product_vectors 와 product 를 조인해 cosine_distance 를 계산
    * -> (product_id, '브랜드 상품명', distance) 를 고르는 Select (정렬·LIMIT 없음)
    """
    if kind == "chunk":
        return (
            select(
                ChunkVector.purchase_id,
                Chunk.body,
                ChunkVector.vector.cosine_distance(q_vec).label("distance"),
            )
            .select_from(ChunkVector)
            .join(
                Chunk,
                and_(Chunk.purchase_id == ChunkVector.purchase_id, Chunk.chunk_index == ChunkVector.chunk_index),
            )
        )

    if kind == "product":
        return (
            select(
                ProductVector.product_id,
                (Product.brand + " " + Product.name).label("body"),
                ProductVector.vector.cosine_distance(q_vec).label("distance"),
            )
            .select_from(ProductVector)
            .join(Product, Product.product_id == ProductVector.product_id)
        )

    if kind == "customer":
        # customer_vectors는 그 고객 리뷰들의 평균이라 원문 자체가 없다.
        return select(
            CustomerVector.customer_id,
            literal("(집계 벡터 - 원문 없음)").label("body"),
            CustomerVector.vector.cosine_distance(q_vec).label("distance"),
        )

    raise ValueError(f"모르는 kind: {kind}")


def inspect(con: Connection, kind: str, questions: list[str], top_k: int = 3) -> None:
    """
    # Summary
    * 질문마다 kind 벡터 테이블에서 코사인 거리로 top_k개를 찾아 화면에 찍는다
    # params
    * con: 읽을 DB 커넥션
    * kind: chunk / product / customer
    * questions: 검색할 질문들
    * top_k: 질문마다 찍을 개수
    # examples
    * kind='chunk', ['관절 좋은 사료'] -> 질문 임베딩, 거리순 top_k*5 조회, id 당 최소 거리만 남김
    * -> 화면에 '[유사도] id=... :: 본문' 을 top_k 줄 출력
    """
    table = _TABLE.get(kind)
    if table is None:
        print(f"[6단계] 모르는 kind '{kind}' 라 건너뜁니다.")
        return

    if not sa_inspect(con).has_table(table):
        print(f"[6단계] {table} 테이블이 없어 '{kind}' 검색을 건너뜁니다.")
        return

    for question in questions:
        started = time.time()
        # 실제 검색(vector_db.search)과 같은 embed_query를 쓴다 - 여기만 접두사를 빼면
        # e5 계열에서 이 화면과 진짜 검색 결과가 달라져서, 눈으로 확인하는 의미가 없어진다.
        stmt = _stmt_for(kind, embed_query(question))
        rows = con.execute(stmt.order_by("distance").limit(top_k * 5)).all()

        best = {}
        for row_id, body, distance in rows:
            if row_id not in best or distance < best[row_id][1]:
                best[row_id] = (body, distance)
        ranked = sorted(best.items(), key=lambda item: item[1][1])[:top_k]

        elapsed = time.time() - started
        print(f"\n[6단계-{kind}] 질문: {question}  ({elapsed:.2f}초)")
        for row_id, (body, distance) in ranked:
            print(f"  [{1 - distance:.3f}] id={row_id} :: {str(body)[:60]}")
