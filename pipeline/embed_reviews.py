# Last Updated : 2026-08-26

""" chunks 테이블의 조각을 문장 임베딩 벡터로 변환해 chunk_vectors 테이블에 저장한다.

    조각을 만드는 일은 chunk.py 가 한다. 여기는 그 결과를 읽어 벡터로 바꾸기만 한다.
    자르는 건 몇 초, 임베딩은 모델 로딩 포함 수십 초 - 값이 다른 작업이라 나눠 두었다.
    한 파일에 두면 자른 결과만 확인하고 싶을 때도 임베딩을 통째로 다시 만들게 된다.

    이 파일은 지휘만 한다.
    어떻게 벡터로 바꾸는지는 prep/embedding.py 가 알고,
    어디에 어떤 모양으로 넣는지는 prep/storage.py 가 안다.
    여기는 그 둘을 순서대로 부르고, 둘 다 모르는 값(색인 대상의 지문)만 계산해 넘긴다.

    검색은 query.py 를 쓴다.
"""

import sqlite3
from app.core.embedder import get_embeddings
from app.core.config import DB_PATH, EMBED_MODEL, EMBED_BATCH_SIZE,EMBED_NORMALIZE
from pipeline.prep import embedding,storage

def fetch_chunks(cur: sqlite3.Cursor) -> list[sqlite3.Row]:
    """색인 대상 조각을 chunks 테이블에서 읽어온다.
    chunk.py가 먼저 돌아 chunks 테이블을 만들어둔 상태여야 한다."""

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
        raise SystemExit("색인할 리뷰가 없습니다. 먼저 chunk.py 를 실행하세요.")

    # 1. prep.embedding으로 문장을 조립 'body'는 이미 잘린 텍스트이므로 조립필요없음
    docs = [chunk['body'] for chunk in chunks]

    # 2. 모델로 벡터화 (+) 벡터 정규화
    model = get_embeddings()
    vectors = model.encode(
        docs, batch_size=32, normalize_embeddings=True, show_progress_bar=True
    )
    # 3. 저장
    storage.save_vectors(
        con, chunks, vectors, vectors.shape[1]
    )
    print(f"\n임베딩 {len(chunks)}개, 차원 {vectors.shape[1]}, 모델 : {EMBED_MODEL}")
    print("검색은 query.py 를 실행하세요.")

    con.close()


if __name__ == "__main__":
    main()
