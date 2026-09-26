# Last Updated : 2026-09-25

"""5단계 검증에 필요한 데이터를 만든다: holdout 지정 + product_vectors + customer_vectors.

예전엔 로컬 SQLite(pet_reco.db)에 BLOB 으로 썼는데, DB 가 Supabase(Postgres)로 이관되면서
pgvector 의 vector 컬럼에 쓴다. 연결은 load_csv/chunk/embed 와 같은 app.core.db.get_engine() 이다.
"""

import sys
from collections import defaultdict

import numpy as np
from sqlalchemy import Connection, Select, delete, func, insert, null, select, text, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased

from app.core.config import EMBED_DIM
from app.core.db import get_engine
from app.core.embedder import embed_documents
from app.domain.embedding_text import product_text
from app.services.embedding_sync import fingerprint
from app.models.chunk import ChunkVector, CustomerVector, ProductVector
from app.models.pet import Pet
from app.models.product import (
    FeedingPurpose,
    Ingredient,
    Product,
    ProductCategory,
    ProductFeedingPurpose,
    ProductIngredient,
)
from app.models.purchase import Purchase, Review


def mark_holdout(con: Connection):
    """
    # Summary
    * 고객별 최근 구매(리뷰 있는 것 중) 1건을 홀드아웃으로 표시한다
    # params
    * con: 쓸 DB 커넥션 (트랜잭션 안)
    # examples
    * con -> 전부 is_holdout=0 으로 되돌린 뒤, 고객별 최근 구매(본문 있는 리뷰) 1건을 골라 1 로
    * -> 고객 수만큼 review.is_holdout=1. 건수 출력
    """
    con.execute(update(Review).values(is_holdout=0))

    ranked = (
        select(
            Review.purchase_id,
            func.row_number()
            .over(
                partition_by=Pet.user_id,
                order_by=(Purchase.purchased_at.desc(), Purchase.purchase_id.desc()),
            )
            .label("rn"),
        )
        .select_from(Review)
        .join(Purchase, Purchase.purchase_id == Review.purchase_id)
        .join(Pet, Pet.pet_id == Purchase.pet_id)
        .where(func.trim(Review.body) != "")
        .subquery("ranked")
    )
    con.execute(
        update(Review)
        .where(Review.purchase_id.in_(select(ranked.c.purchase_id).where(ranked.c.rn == 1)))
        .values(is_holdout=1)
    )
    n = con.execute(select(func.count()).select_from(Review).where(Review.is_holdout == 1)).scalar_one()
    print(f"[holdout] 고객 {n}명의 최근 구매를 홀드아웃으로 표시")


def product_rows_stmt() -> Select:
    """
    # Summary
    * product_text()가 받는 모양대로 상품 한 개를 한 행으로 모은다
    # info
    * tests/scratch.py 도 쓴다
    # examples
    * 인자 없음 -> product 에 카테고리·급여목적·원료를 outerjoin, 다대다는 string_agg
    * -> 상품당 1행 {product_id, brand, product_name, category, ingredients, ...} 을 고르는 Select
    """
    pc_parent = aliased(ProductCategory, name="pc_parent")
    # Postgres 는 GROUP BY 에 없는 컬럼을 고르면 에러라서, 카테고리 두 표의 PK 도
    # GROUP BY 에 넣는다(행 수는 그대로 상품당 1행).
    return (
        select(
            Product.product_id,
            Product.brand,
            Product.name.label("product_name"),
            pc_parent.name_ko.label("category"),
            ProductCategory.name_ko.label("sub_category"),
            func.string_agg(FeedingPurpose.name_ko.distinct(), ",").label("target_feeding_purpose"),
            Product.food_form.label("target_food_form"),
            func.string_agg(Ingredient.name_ko.distinct(), ",").label("ingredients"),
            null().label("tags"),
            Product.description,
        )
        .select_from(Product)
        .outerjoin(ProductCategory, ProductCategory.product_category_id == Product.product_category_id)
        .outerjoin(pc_parent, pc_parent.product_category_id == ProductCategory.parent_id)
        .outerjoin(ProductFeedingPurpose, ProductFeedingPurpose.product_id == Product.product_id)
        .outerjoin(FeedingPurpose, FeedingPurpose.feeding_purpose_id == ProductFeedingPurpose.feeding_purpose_id)
        .outerjoin(ProductIngredient, ProductIngredient.product_id == Product.product_id)
        .outerjoin(Ingredient, Ingredient.ingredient_id == ProductIngredient.ingredient_id)
        .group_by(Product.product_id, ProductCategory.product_category_id, pc_parent.product_category_id)
    )


def recreate(con: Connection, model) -> None:
    """
    # Summary
    * 벡터 표를 지우고 새로 만든다
    # info
    * 차원이 EMBED_DIM 에 묶여 있어 모델을 바꾸면 다시 만들어야 한다
    # params
    * con: 쓸 DB 커넥션 (트랜잭션 안)
    * model: ProductVector / CustomerVector
    # examples
    * (con, ProductVector) -> vector 확장 확인 후 표를 DROP 하고 다시 CREATE
    * -> 빈 product_vectors 표
    """
    # pgvector 확장이 없으면 vector 컬럼 자체를 못 만든다 - 최초 1회만 실제로 동작한다.
    con.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    model.__table__.drop(con, checkfirst=True)
    model.__table__.create(con)


def known_product_hashes(con: Connection) -> dict[int, str] | None:
    """
    # Summary
    * 저장된 {product_id: 지문}. 표를 그대로 이어 쓸 수 없으면 None 을 돌려준다
    # info
    * None 인 경우: 표가 없다 / source_hash 컬럼이 없는 옛 표다 / 저장된 차원이 EMBED_DIM 과 다르다
    * 차원이 다르면 upsert 자체가 실패하므로 지문을 비교하기 전에 표부터 새로 만들어야 한다
    # params
    * con: 읽을 DB 커넥션
    # examples
    * con -> 표·source_hash 컬럼·차원을 확인하고 (product_id, source_hash) 를 읽음
    * -> {1: 'ab12...', 2: 'cd34...'} 또는 None (다시 만들어야 함)
    """
    insp = sa_inspect(con)
    if not insp.has_table(ProductVector.__tablename__):
        return None
    if "source_hash" not in {c["name"] for c in insp.get_columns(ProductVector.__tablename__)}:
        return None
    dim = con.execute(select(func.vector_dims(ProductVector.vector)).limit(1)).scalar()
    if dim is not None and dim != EMBED_DIM:
        return None
    return dict(con.execute(select(ProductVector.product_id, ProductVector.source_hash)).all())


def build_product_vectors(con: Connection):
    """
    # Summary
    * product를 문장으로 임베딩해 product_vectors에 저장한다
    * 문장이 바뀐 상품만 다시 임베딩한다
    # params
    * con: 쓸 DB 커넥션 (트랜잭션 안)
    # examples
    * 상품 200개 중 3개 문장이 바뀜 -> 지문 비교로 3개만 임베딩해 upsert, 사라진 상품은 delete
    * -> '[product_vectors] 상품 200개 / 새로 3 / 그대로 197 / 지움 0'
    """
    products = [dict(row) for row in con.execute(product_rows_stmt()).mappings()]
    texts = [product_text(p) for p in products]
    marks = [fingerprint(t) for t in texts]

    known = known_product_hashes(con)
    if known is None:
        recreate(con, ProductVector)
        known = {}

    # 처음 보는 상품은 known.get() 이 None 이라 자동으로 '다름'이 된다. 모델이 바뀌어도 지문이 달라진다.
    todo = [i for i, (p, mark) in enumerate(zip(products, marks)) if known.get(p["product_id"]) != mark]

    # 돈과 시간이 드는 자리는 여기 하나뿐이다. 고른 것만 모델에 넘긴다.
    if todo:
        vectors = embed_documents([texts[i] for i in todo])
        stmt = pg_insert(ProductVector).values(
            [
                {"product_id": products[i]["product_id"], "vector": v, "source_hash": marks[i]}
                for i, v in zip(todo, vectors)
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["product_id"],
            set_={"vector": stmt.excluded.vector, "source_hash": stmt.excluded.source_hash},
        )
        con.execute(stmt)

    # 표엔 있는데 지금 상품 목록엔 없는 것 = 원본에서 사라진 상품.
    alive = {p["product_id"] for p in products}
    gone = [pid for pid in known if pid not in alive]
    if gone:
        con.execute(delete(ProductVector).where(ProductVector.product_id.in_(gone)))

    print(
        f"[product_vectors] 상품 {len(products)}개 / 새로 {len(todo)} "
        f"/ 그대로 {len(products) - len(todo)} / 지움 {len(gone)}"
    )


def build_customer_vectors(con: Connection):
    """
    # Summary
    * 고객 벡터 = 홀드아웃을 뺀 그 고객 리뷰 조각 벡터의 평균
    # info
    * 홀드아웃을 빼는 건 정답을 미리 보지 않기 위해서다
    # params
    * con: 쓸 DB 커넥션 (트랜잭션 안)
    # examples
    * con -> is_holdout=0 리뷰의 chunk_vectors 를 고객별로 모아 평균·정규화
    * -> customer_vectors 를 새로 만들어 고객당 1행 저장
    """
    rows = con.execute(
        select(Pet.user_id, ChunkVector.vector)
        .select_from(Purchase)
        .join(Pet, Pet.pet_id == Purchase.pet_id)
        .join(Review, Review.purchase_id == Purchase.purchase_id)
        .join(ChunkVector, ChunkVector.purchase_id == Purchase.purchase_id)
        .where(Review.is_holdout == 0)
    ).all()

    buckets = defaultdict(list)
    for user_id, vec in rows:
        buckets[user_id].append(np.asarray(vec, dtype=np.float32))

    recreate(con, CustomerVector)
    params = []
    for user_id, vecs in buckets.items():
        mean_vec = np.mean(vecs, axis=0).astype(np.float32)
        mean_vec /= np.linalg.norm(mean_vec) + 1e-9
        params.append({"customer_id": user_id, "vector": mean_vec})
    if params:
        con.execute(insert(CustomerVector), params)
    print(f"[customer_vectors] 고객 {len(buckets)}명 벡터 저장")


def main():
    """
    # Summary
    * 홀드아웃 표시와 벡터 빌드 사이에는 chunk.py -> embed.py 가 끼어야 한다
    # info
    * mark_holdout 이 색인 대상(INDEX_FILTER 의 is_holdout=0)을 바꾸고,
      build_customer_vectors 는 그 색인 결과인 chunk_vectors 를 읽기 때문이다.
      한 번에 돌리면 낡은 벡터로 고객 벡터를 만든다
    * 실행 순서
        python -m pipeline.prep_rec holdout
        python -m pipeline.chunk
        python -m pipeline.embed
        python -m pipeline.prep_rec vectors
    # examples
    * 'holdout' / 'vectors' / 'all'(기본) -> 단계마다 트랜잭션을 따로 열어 실행
    * -> holdout 은 mark_holdout, vectors 는 상품·고객 벡터 빌드
    """
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    # 단계마다 따로 커밋한다 - 벡터 빌드가 실패해도 앞 단계의 홀드아웃 표시는 남는다.
    if step in ("holdout", "all"):
        with get_engine().begin() as con:
            mark_holdout(con)
    if step in ("vectors", "all"):
        with get_engine().begin() as con:
            build_product_vectors(con)
            build_customer_vectors(con)


if __name__ == "__main__":
    main()
