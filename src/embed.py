# Last updated: 2026-08-12
# pet_purchases 의 반려견 리뷰를 문장 임베딩 벡터로 변환해 review_vectors 테이블에 저장하는 스크립트
#
# 리뷰 본문만 넣지 않고 "어떤 강아지가 / 어떤 상품에 대해" 남긴 후기인지를 함께 문장으로 붙인다.
# 검색 단계에서 "닭고기 알레르기가 있는 소형견"처럼 프로필을 담은 질의가 들어왔을 때
# 조건이 맞는 리뷰가 의미적으로도 가깝게 걸리도록 하기 위함이다.
import json
import sqlite3
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent  # 실행 위치와 무관하게 프로젝트 루트를 기준으로 함
DB_PATH = ROOT / 'pet_reco.db'

# 다국어 지원 모델(한국어 포함) - 문장을 고정 차원 벡터로 변환
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'


def fmt_purchase_id(pid):
    """정수 purchase_id 를 사람이 읽기 쉬운 원래 표기로 되돌린다. 418 -> 'O00418'

    저장은 INTEGER로 하되(조인/인덱스에 유리) 화면에 찍을 때만 접두어를 붙인다.
    검색 결과에 ID만 덩그러니 나오면 어느 테이블 것인지 알아보기 어렵기 때문이다.
    """
    return f'O{pid:05d}'


def build_doc(row):
    """리뷰 한 건을 임베딩용 문장으로 조립한다."""
    # 알레르기/건강 이상이 없는 경우 CSV가 빈 값이라 NULL로 들어온다 -> 명시적인 한국어로 바꿔준다
    allergy = row['allergy'] or '알레르기 없음'
    health = row['health_condition'] or '건강 특이사항 없음'
    return (
        f"{row['size_category']}견 {row['age_group']} {row['breed']}, {allergy}, {health}. "
        f"{row['category']}/{row['sub_category']} {row['product_name']} "
        f"({row['target_feeding_purpose']} 목적, {row['target_food_form']}) "
        f"별점 {row['rating']}점 후기: {row['review']}"
    )


def fetch_rows(cur):
    """색인 대상 리뷰를 상품 정보와 함께 읽어온다."""
    cur.row_factory = sqlite3.Row
    return cur.execute("""
        SELECT
            p.purchase_id, p.category, p.breed, p.size_category, p.age_group,
            p.allergy, p.health_condition, p.rating, p.review,
            pr.sub_category, pr.product_name,
            pr.target_feeding_purpose, pr.target_food_form
        FROM pet_purchases AS p
        JOIN pet_products AS pr ON pr.product_id = p.product_id
        WHERE p.is_holdout = 0
          AND p.review IS NOT NULL
          AND TRIM(p.review) <> ''
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
    # 어떤 모델/차원으로 만든 벡터인지 남겨둔다. 모델을 바꾸면 검색 쪽에서 불일치를 감지할 수 있다.
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
        [('model', MODEL_NAME), ('dim', str(dim)), ('count', str(len(rows)))],
    )
    con.commit()


def search(con, model, query, where='1=1', params=(), top_k=3):
    """저장된 벡터로 유사 리뷰를 찾아보는 확인용 검색.

    벡터 유사도만으로는 "소형견", "닭고기 알레르기 없음" 같은 조건이 지켜지지 않는다.
    (의미가 비슷하기만 하면 대형견 리뷰도 상위에 올라온다.)
    그래서 where 로 pet_purchases 를 먼저 걸러낸 뒤, 남은 후보만 유사도로 정렬한다.
    실제 추천 API도 이 순서(프로필 필터 -> 벡터 랭킹)를 따라야 한다.
    """
    rows = con.execute(f"""
        SELECT v.purchase_id, v.doc, v.vector
        FROM review_vectors AS v
        JOIN pet_purchases AS p ON p.purchase_id = v.purchase_id
        WHERE {where}
    """, params).fetchall()
    if not rows:
        return []
    # 저장할 때 정규화했으므로 내적만으로 코사인 유사도가 된다
    matrix = np.array([json.loads(r[2]) for r in rows], dtype=np.float32)
    q = model.encode([query], normalize_embeddings=True)[0]
    scores = matrix @ q
    return [(rows[i][0], float(scores[i]), rows[i][1]) for i in np.argsort(-scores)[:top_k]]


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

    # 프로필을 담은 질의가 실제로 관련 리뷰를 찾아오는지 확인
    #demo = '닭고기 알레르기가 있는 소형견인데 피부 가려움에 괜찮았던 사료'
    demo = '이빨이 약한 대형견을 위한 사료를 추천해줘.'
    print(f'\n[확인용 검색] {demo}')

    print('  1) 벡터 유사도만 사용 - 조건이 지켜지지 않음')
    for pid, score, doc in search(con, model, demo):
        print(f'     {fmt_purchase_id(pid)} ({score:.3f}) {doc[:70]}...')

    print('  2) 프로필 필터 + 벡터 유사도 - 실제 추천에 쓸 방식')
    hits = search(
        con, model, demo,
        #where="p.size_category = ? AND (p.allergy IS NULL OR p.allergy <> ?)",
        #params=('소형', '닭고기 알레르기'),
        where="p.size_category = ? AND (p.allergy IS NULL OR p.allergy <> ?)",
        params=('대형', '닭고기 알레르기'),
    )
    for pid, score, doc in hits:
        print(f'     {fmt_purchase_id(pid)} ({score:.3f}) {doc[:70]}...')

    con.close()


if __name__ == '__main__':
    main()
