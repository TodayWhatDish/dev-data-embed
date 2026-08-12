# Last updated: 2026-08-12
# purchases 테이블의 화장품 리뷰를 문장 임베딩 벡터로 변환해 review_vectors 테이블에 저장하는 스크립트
import json
import sqlite3

from sentence_transformers import SentenceTransformer

con = sqlite3.connect('selectory.db')
cur = con.cursor()

# 다국어 지원 모델(한국어 포함) - 문장을 고정 차원 벡터로 변환
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# 화장품 카테고리 리뷰만 대상으로 함
rows = cur.execute("""
    SELECT purchase_id, sub_category, user_trait, review
    FROM purchases
    WHERE category = 'Cosmetics'
""").fetchall()


# "세부카테고리/피부타입 후기: 리뷰내용" 형태로 문맥을 붙여 임베딩 품질을 높임
docs = [f"{sub}/{trait} 후기: {review}" for _, sub, trait, review in rows]
# normalize_embeddings=True -> 벡터 길이를 1로 맞춰서 이후 코사인 유사도 계산이 내적만으로 가능해짐
V = model.encode(docs, batch_size=32, normalize_embeddings=True)

# purchase_id -> 임베딩 벡터(JSON 문자열) 매핑 테이블
cur.execute("""
CREATE TABLE IF NOT EXISTS review_vectors (
    purchase_id TEXT PRIMARY KEY,
    vector TEXT
)
""")
cur.execute("DELETE FROM review_vectors")  # 재실행 시 중복 방지를 위해 기존 데이터 초기화

for (pid, _, _, _), vec in zip(rows, V):
    cur.execute(
        "INSERT INTO review_vectors VALUES (?, ?)",
        (pid, json.dumps(vec.tolist())),  # numpy 배열 -> list -> JSON 문자열로 저장 (SQLite엔 벡터 타입이 없어서)
    )

con.commit()
print(f"임베딩 {len(rows)}개, 차원 {V.shape[1]}")
print(cur.execute("SELECT COUNT(*) FROM review_vectors").fetchone()[0])
con.close()