# Last Updated : 2026-08-24

"""조각과 벡터를 DB에 적재한다.

무엇을 넣을지 알게된다 (함수 인자 chunks, vectors로 이미 완성되어 넘어오기 때문)
그게 어떻게 만들어졌는지는 모른다. 즉, 자르거나 임베딩하는 법은 해당 문서에 존재하지 않는다.

"""

import json
import sqlite3
import numpy as np
from app.core.config import EMBED_MODEL


# 청킹한 리뷰를 db로 만들기
def save_chunks(con: sqlite3.Connection, chunks: list[dict]):
    cur = con.cursor()

    # chunks 테이블은 매번 지우고 다시 생성
    cur.execute("DROP TABLE IF EXISTS chunks")
    cur.execute("""
    CREATE TABLE chunks (
        purchase_id INTEGER NOT NULL,
        chunk_index INTEGER NOT NULL,
        body TEXT,
        n_tokens INTEGER,
        PRIMARY KEY (purchase_id, chunk_index)
    )
    """)
    # (purchase_id, chunk_index) 한 쌍이 식별자, 벡터도 이 쌍으로 붙는다.
    cur.executemany(
        "INSERT INTO chunks VALUES (?, ?, ?, ?)",
        [
            (
                chunk["purchase_id"],
                chunk["chunk_index"],
                chunk["body"],
                chunk["n_tokens"],
            )
            for chunk in chunks
        ],
    )
    con.commit()


# 적재한 조각을 다시 꺼낸다. build_index.py 가 벡터로 바꿀 대상을 읽는 자리.
def load_chunks(con: sqlite3.Connection):
    """chunks 테이블의 조각 전체를 (purchase_id, chunk_index, body) 로 읽어온다.

    읽기는 이 파일의 역할("적재")을 조금 넘지만, chunks 의 컬럼 이름을 아는 코드를
    save_chunks 와 한자리에 모아두려고 여기 둔다. 스키마가 바뀌면 고칠 데가 한 파일이다.

    조각 순서(purchase_id, chunk_index)는 save_vectors 가 벡터와 자리 맞춰 zip 하므로,
    읽은 목록을 그대로 넘겨야 한다. 중간에 걸러내거나 재정렬하면 벡터가 어긋난다.
    """
    cur = con.cursor()
    # 컬럼 이름으로 꺼내야 부르는 쪽이 chunk['body'] 처럼 읽을 수 있다.
    cur.row_factory = sqlite3.Row
    return cur.execute("""
        SELECT purchase_id, chunk_index, body
        FROM chunks
        ORDER BY purchase_id, chunk_index
    """).fetchall()


def save_vectors(
    con: sqlite3.Connection, chunks: list[dict], vectors: np.ndarray, dim, source: str
):
    """chunk_vectors 테이블을 만들고 벡터에 적재한다. save_chunks가 선행되어야 함"""

    # 청크와 벡터의 수가 다를 시 방어 로직
    if len(chunks) != len(vectors):
        raise ValueError(
            f"조각 {len(chunks)}개와 벡터 {len(vectors)}개의 수가 다릅니다."
        )

    cur = con.cursor()

    # chunks 테이블이 없을 시 오류
    if not cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"
    ).fetchone():
        raise ValueError("chunks 테이블이 없습니다. save_chunks 를 먼저 실행하세요.")

    # chunk_vectors 테이블을 매번 다시 만든다.
    cur.execute("DROP TABLE IF EXISTS chunk_vectors")
    cur.execute("""
    CREATE TABLE chunk_vectors (
        purchase_id INTEGER NOT NULL,
        chunk_index INTEGER NOT NULL,
        vector TEXT,
        PRIMARY KEY (purchase_id, chunk_index),
        FOREIGN KEY (purchase_id, chunk_index) REFERENCES chunks (purchase_id, chunk_index)
    )
    """)
    # 어떤 모델/차원으로, 어떤 상태의 데이터로 만든 벡터인지 남겨둔다.
    # 검색 쪽이 시작할 때 이 값과 현재 DB를 비교해 재색인 필요를 알린다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS embedding_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    cur.executemany(
        "INSERT INTO chunk_vectors VALUES (?, ?, ?)",
        [
            # numpy 배열 -> list -> JSON 문자열로 저장 (SQLite엔 벡터 타입이 없어서)
            (chunk["purchase_id"], chunk["chunk_index"], json.dumps(vec.tolist()))
            for chunk, vec in zip(chunks, vectors)
        ],
    )
    # source(색인 대상 데이터의 지문)는 부르는 쪽에서 계산해 넘겨준다.
    # 여기는 무엇을 넣을지만 알고 그게 어떻게 만들어졌는지는 모르는 자리이기 때문이다.
    cur.executemany(
        "INSERT OR REPLACE INTO embedding_meta VALUES (?, ?)",
        [
            ("model", EMBED_MODEL),
            ("dim", str(dim)),
            ("count", str(len(chunks))),
            ("source", source),
        ],
    )
    con.commit()




