# Last updated: 2026-09-23
# Last Updated : 2026-08-24

"""리뷰를 임베딩용 문서로 조립하고(embedding) 토큰 한도에 맞게 자른다(chunking).

자르는 건 몇 초, 임베딩은 모델 로딩 포함 수십 초 - 값이 다른 작업이라 나눴다.
DB는 Supabase(Postgres) - app.core.db.engine 하나로 관계형 테이블과 chunks 를 같이 읽고 쓴다.
"""

import statistics
import sys

# 터미널에 출력할 수 없는 특수 이모지나 기호 등을 대체문자로 변경하여 오류를 방지
sys.stdout.reconfigure(errors="replace")

from sqlalchemy import text

from app.core.config import EMBED_MAX_TOKENS, EMBED_PROVIDER, INDEX_FILTER, SIZE_CASE

# transformers는 provider='st'(로컬)에서만 깔린다(pyproject.toml 'local' 그룹) - openai 배포
# 환경엔 없어 import 자체가 실패한다. 순수 로그 억제용이라 없으면 그냥 넘어간다.
#
# ponytail: pipeline/prep/chunking.py:25 와 같은 이유로 sentence_transformers/transformers 는
# langchain_text_splitters 보다 먼저, 그리고 provider='st'일 때만 import 해야 한다 - 순서가
# 어긋나면 numpy/pyarrow 조합에서 프로세스가 죽는다(access violation).
if EMBED_PROVIDER != "openai":
    try:
        from transformers import logging as hf_logging

        hf_logging.set_verbosity_error()
    except ImportError:
        pass
from app.core.db import Base, engine
from app.models.chunk import Chunk, ChunkVector  # noqa: F401 (Base.metadata 등록용)
from pipeline.prep import chunking

# GROUP_CONCAT(SQLite) -> STRING_AGG(Postgres) 한 곳만 바뀌면 되도록 SQL은 그대로 유지한다.
FETCH_SQL = f"""
    SELECT
        r.purchase_id, r.rating, r.body AS review,
        pu.age_month_at_purchase,
        {SIZE_CASE} AS size_category,
        STRING_AGG(DISTINCT br.name_ko, ',') AS breed,
        STRING_AGG(DISTINCT al.name_ko, ',') AS allergy,
        pc_parent.name_ko AS category, pc.name_ko AS sub_category,
        p.name AS product_name, p.food_form AS target_food_form,
        STRING_AGG(DISTINCT fp.name_ko, ',') AS target_feeding_purpose,
        STRING_AGG(DISTINCT ing.name_ko, ',') AS ingredients
    FROM review AS r
    JOIN purchase AS pu ON pu.purchase_id = r.purchase_id
    JOIN pet AS pe ON pe.pet_id = pu.pet_id
    JOIN product AS p ON p.product_id = pu.product_id
    LEFT JOIN pet_breed AS pb ON pb.pet_id = pe.pet_id
    LEFT JOIN breed AS br ON br.breed_id = pb.breed_id
    LEFT JOIN pet_allergy AS pa ON pa.pet_id = pe.pet_id
    LEFT JOIN allergen AS al ON al.allergen_id = pa.allergen_id
    LEFT JOIN product_category AS pc ON pc.product_category_id = p.product_category_id
    LEFT JOIN product_category AS pc_parent ON pc_parent.product_category_id = pc.parent_id
    LEFT JOIN product_feeding_purpose AS pfp ON pfp.product_id = p.product_id
    LEFT JOIN feeding_purpose AS fp ON fp.feeding_purpose_id = pfp.feeding_purpose_id
    LEFT JOIN product_ingredient AS pi ON pi.product_id = p.product_id
    LEFT JOIN ingredient AS ing ON ing.ingredient_id = pi.ingredient_id
    WHERE {INDEX_FILTER}
    GROUP BY r.purchase_id, r.rating, r.body, pu.age_month_at_purchase, pu.size_at_purchase,
             pc_parent.name_ko, pc.name_ko, p.name, p.food_form
    ORDER BY r.purchase_id
"""


def fetch_rows(conn):
    """
    # Summary
    * 자를 대상 리뷰를 펫·상품 정보와 함께 읽어온다
    # info
    * 대상 조건인 INDEX_FILTER는 config.py에 명시
    * 새 스키마는 정규화돼 있어 견종/알러지/급여목적이 전부 다대다다.
      한 리뷰당 여러 행으로 불어나는 걸 STRING_AGG(DISTINCT ...)로 다시 한 줄로 뭉친다
    # params
    * conn: 읽을 DB 커넥션
    # examples
    * conn -> INDEX_FILTER(is_holdout=0) 리뷰를 펫·상품과 조인, 다대다는 STRING_AGG 로 합침
    * -> 리뷰당 1행 [{purchase_id, rating, review, breed: '말티즈,푸들', ingredients, ...}, ...]
    """
    return conn.execute(text(FETCH_SQL)).mappings().all()


def save_chunks(conn, chunks: list[dict]):
    """
    # Summary
    * chunks 테이블을 비우고 새로 채운다. 조각과 벡터는 (purchase_id, chunk_index)로 묶인다
    # info
    * chunk_vectors가 (purchase_id, chunk_index)로 chunks를 FK 참조하므로, chunks를 먼저 지우면
      DependentObjectsStillExist로 막힌다 - 옛 벡터도 어차피 새 조각과 안 맞으니 먼저 지운다
    * 재임베딩은 embed.py가 담당, 여기서 새로 만들지 않는다
    # params
    * conn: 쓸 DB 커넥션 (트랜잭션 안)
    * chunks: chunking.split_reviews()가 만든 조각 목록
    # examples
    * chunks 목록 -> chunk_vectors·chunks 를 DROP 후 chunks 를 다시 만들어 INSERT
    * -> chunks 테이블이 새 조각으로 교체됨. chunk_vectors 는 비어 있음(embed.py 가 채움)
    """
    Base.metadata.tables["chunk_vectors"].drop(conn, checkfirst=True)
    table = Base.metadata.tables["chunks"]
    table.drop(conn, checkfirst=True)
    table.create(conn, checkfirst=True)
    conn.execute(table.insert(), chunks)


def main():
    with engine.begin() as conn:
        rows = fetch_rows(conn)
        if not rows:
            raise SystemExit("자를 리뷰가 없습니다. 먼저 python -m pipeline.load_csv 를 실행하세요.")

        # (purchase_id, 문서) 쌍으로 넘긴다. 한 리뷰가 조각 여러 개로 쪼개져도
        # 그 조각이 원래 어느 리뷰에서 나왔는지 따라붙어야 하기 때문이다.
        docs = [(row["purchase_id"], chunking.build_review_doc(row), row["product_name"]) for row in rows]
        chunks = chunking.split_reviews(docs)
        save_chunks(conn, chunks)

    # 자른 결과가 멀쩡한지는 눈으로 봐야 안다. 토큰 분포를 요약해 남긴다.
    tokens = [chunk["n_tokens"] for chunk in chunks]
    print(f"\n리뷰 {len(rows)}건 -> 조각 {len(chunks)}개 (쪼개지며 늘어난 조각 {len(chunks) - len(rows)}개)")
    print(
        f"토큰 평균 {statistics.mean(tokens):.1f} / 중앙값 {statistics.median(tokens):.0f} / 최대 {max(tokens)}"
    )

    # CHUNK_SIZE 안으로 잘랐으니 여기 걸리면 안 된다. 걸린다면 자르기가 제 몫을 못 한 것이고,
    # 그대로 두면 임베딩 때 뒤가 조용히 잘려나간다.
    over = sum(1 for n in tokens if n > EMBED_MAX_TOKENS)
    if over:
        print(f"주의: 모델 한도({EMBED_MAX_TOKENS} 토큰)를 넘는 조각 {over}개 - 뒤가 잘려 누락된다")

    print("벡터는 여기서 만들지 않는다. 이어서 python -m pipeline.embed 를 실행하세요.")


if __name__ == "__main__":
    main()
