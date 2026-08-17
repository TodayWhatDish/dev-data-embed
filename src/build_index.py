# Last updated: 2026-08-17
# pet_purchases 의 반려견 리뷰를 문장 임베딩 벡터로 변환해 review_vectors 테이블에 저장하는 스크립트
#
# 이 파일은 색인(벡터 사전 계산)만 한다. 저장된 벡터로 검색하는 쪽은 search.py 에 있다.
# 인코딩이 십수 초 걸리므로 데이터나 모델이 바뀔 때만 실행하고, 평소 검색은 query.py 를 쓴다.
#
# 리뷰 본문만 넣지 않고 "어떤 강아지가 / 어떤 상품에 대해" 남긴 후기인지를 함께 문장으로 붙인다.
'''
LLM에 이런 형태로 넘기면 되지 않을까
[자료]
임베딩에서 긁어온 추천 근거(리뷰) 자료들

[대상]
품종: {강아지 품종}
크기: {강아지 크기}
... 어떤 정형 데이터

[사용자 추가 요구 및 질문 사항]
{query}
'''

# 검색 단계에서 "닭고기 알레르기가 있는 소형견"처럼 프로필을 담은 질의가 들어왔을 때
# 조건이 맞는 리뷰가 의미적으로도 가깝게 걸리도록 하기 위함이다.
import json
import sqlite3

from sentence_transformers import SentenceTransformer
from config import DB_PATH,MODEL_NAME,INDEX_FILTER,source_fingerprint


def build_doc(row):
    """리뷰 한 건을 임베딩용 문장으로 조립한다."""
    # 알레르기/건강 이상이 없는 경우 CSV가 빈 값이라 NULL로 들어온다 -> 명시적인 한국어로 바꿔준다
    allergy = row['allergy'] or '알레르기 없음'
    health = row['health_condition'] or '건강 특이사항 없음'
    return (
        "passage:\n"
        f"{row['size_category']}견 {row['age_group']} {row['breed']}, {allergy}, {health}. "
        f"{row['category']}/{row['sub_category']} {row['product_name']} "
        f"({row['target_feeding_purpose']} 목적, {row['target_food_form']}) "
        f"별점 {row['rating']}점 후기: {row['review']}"
    )


def fetch_rows(cur):
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


def save_vectors(con, rows, docs, vectors, dim):
    cur = con.cursor()

    # purchase_id -> 임베딩 문장 + 벡터(JSON 문자열) 매핑 테이블
    # purchase_id 는 pet_purchases 와 같은 INTEGER 여야 조인이 성립한다.
    # IF NOT EXISTS 로 두면 예전 실행이 만든 TEXT 컬럼이 그대로 남아
    # 정수 418 이 문자열 '418' 로 저장되고 조인이 조용히 실패한다. 그래서 매번 다시 만든다.
    cur.execute('DROP TABLE IF EXISTS review_vectors')
    cur.execute("""
    CREATE TABLE review_vectors (
        purchase_id INTEGER PRIMARY KEY,
        doc TEXT,
        vector TEXT
    )
    """)
    # 어떤 모델/차원으로, 어떤 상태의 데이터로 만든 벡터인지 남겨둔다.
    # search.py 의 VectorStore 가 시작할 때 이 값과 현재 DB를 비교해 재색인 필요를 알린다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS embedding_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    cur.executemany(
        'INSERT INTO review_vectors VALUES (?, ?, ?)',
        [
            # numpy 배열 -> list -> JSON 문자열로 저장 (SQLite엔 벡터 타입이 없어서)
            (row['purchase_id'], doc, json.dumps(vec.tolist()))
            for row, doc, vec in zip(rows, docs, vectors)
        ],
    )
    cur.executemany(
        'INSERT OR REPLACE INTO embedding_meta VALUES (?, ?)',
        [
            ('model', MODEL_NAME),
            ('dim', str(dim)),
            ('count', str(len(rows))),
            ('source', source_fingerprint(con)),
        ],
    )
    con.commit()


def main():
    con = sqlite3.connect(DB_PATH)
    rows = fetch_rows(con.cursor())
    if not rows:
        raise SystemExit('색인할 리뷰가 없습니다. 먼저 load_db.py 를 실행하세요.')

    model = SentenceTransformer(MODEL_NAME)
    docs = [build_doc(row) for row in rows]
    # normalize_embeddings=True -> 벡터 길이를 1로 맞춰서 이후 코사인 유사도 계산이 내적만으로 가능해짐
    vectors = model.encode(docs, batch_size=32, normalize_embeddings=True, show_progress_bar=True)

    save_vectors(con, rows, docs, vectors, vectors.shape[1])
    print(f'\n임베딩 {len(rows)}개, 차원 {vectors.shape[1]}, 모델 {MODEL_NAME}')
    print('검색은 query.py 를 실행하세요.')

    con.close()


if __name__ == '__main__':
    main()
