# Last updated: 2026-08-25

"""chunks 테이블의 조각을 문장 임베딩 벡터로 변환해 chunk_vectors 테이블에 저장한다.
pet_purchases 의 반려견 리뷰를 문장 임베딩 벡터로 변환해 review_vectors 테이블에 저장하는 스크립트

이 파일은 색인(벡터 사전 계산)만 한다. 저장된 벡터로 검색하는 쪽은 search.py 에 있다.
인코딩이 십수 초 걸리므로 데이터나 모델이 바뀔 때만 실행하고, 평소 검색은 query.py 를 쓴다.

리뷰 본문만 넣지 않고 "어떤 강아지가 / 어떤 상품에 대해" 남긴 후기인지를 함께 문장으로 붙인다.

LLM에 이런 형태로 넘기면 되지 않을까
[자료]
임베딩에서 긁어온 추천 근거(리뷰) 자료들

[대상]
품종: {강아지 품종}
크기: {강아지 크기}
... 어떤 정형 데이터

[사용자 추가 요구 및 질문 사항]
{query}
"""

# 검색 단계에서 "닭고기 알레르기가 있는 소형견"처럼 프로필을 담은 질의가 들어왔을 때
# 조건이 맞는 리뷰가 의미적으로도 가깝게 걸리도록 하기 위함이다.
import sqlite3
from app.core.embedder import get_embeddings
from app.core.config import DB_PATH, EMBED_MODEL, INDEX_FILTER
from app.core.db import source_fingerprint
from pipeline.prep import storage


def build_doc(row):
    """리뷰 한 건을 임베딩용 문장으로 조립한다."""
    # 알레르기/건강 이상이 없는 경우 CSV가 빈 값이라 NULL로 들어온다 -> 명시적인 한국어로 바꿔준다
    allergy = row["allergy"] or "알레르기 없음"
    health = row["health_condition"] or "건강 특이사항 없음"
    return (
        "passage:\n"
        f"{row['size_category']}견 {row['age_group']} {row['breed']}, {allergy}, {health}. "
        f"{row['category']}/{row['sub_category']} {row['product_name']} "
        f"({row['target_feeding_purpose']} 목적, {row['target_food_form']}) "
        f"별점 {row['rating']}점 후기: {row['review']}"
    )


def fetch_rows(cur: sqlite3.Cursor) -> list[sqlite3.Row]:
    """색인 대상 리뷰를 상품 정보와 함께 읽어온다.

    대상 조건(INDEX_FILTER)은 config.py 에 있다. 검색 쪽에서 재색인이 필요한지
    판단할 때 같은 조건을 봐야 하므로 여기에 직접 적지 않는다.
    """
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


def fetch_chunks(cur: sqlite3.Cursor) -> list[sqlite3.Row]:
    """색인 대상 조각을 chunks 테이블에서 읽어온다.
    prepare.py가 먼저 돌아 chunks 테이블을 만들어둔 상태여야 한다."""

    cur.row_factory = sqlite3.Row
    return cur.execute("""
        SELECT purchase_id, chunk_index, body, n_tokens
        FROM chunks
        ORDER BY purchase_id, chunk_index
                       """).fetchall()


def main():
    con = sqlite3.connect(DB_PATH)
    chunks = fetch_chunks(con.cursor())
    if not chunks:
        raise SystemExit("색인할 리뷰가 없습니다. 먼저 load_db.py 를 실행하세요.")

    model = get_embeddings()
    bodies = [chunk["body"] for chunk in chunks]
    # normalize_embeddings=True -> 벡터 길이를 1로 맞춰서 이후 코사인 유사도 계산이 내적만으로 가능해짐
    vectors = model.encode(
        bodies, batch_size=32, normalize_embeddings=True, show_progress_bar=True
    )

    storage.save_vectors(
        con, chunks, vectors, vectors.shape[1], source_fingerprint(con)
    )
    print(f"\n임베딩 {len(chunks)}개, 차원 {vectors.shape[1]}, 모델 {EMBED_MODEL}")
    print("검색은 query.py 를 실행하세요.")

    con.close()


if __name__ == "__main__":
    main()
