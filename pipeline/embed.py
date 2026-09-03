# Last Updated : 2026-08-26

""" chunks 테이블의 조각을 문장 임베딩 벡터로 변환해 chunk_vectors 테이블에 저장한다.

    조각을 만드는 일은 chunk.py 가 한다. 여기는 그 결과를 읽어 벡터로 바꾸기만 한다.
    자르는 건 몇 초, 임베딩은 모델 로딩 포함 수십 초 - 값이 다른 작업이라 나눠 두었다.
    한 파일에 두면 자른 결과만 확인하고 싶을 때도 임베딩을 통째로 다시 만들게 된다.

    이 파일은 지휘만 한다.
    무엇을 다시 만들지 고르는 일은 features/embedding_sync.py 가 알고,
    어디에 어떤 모양으로 넣는지는 adapters/stores/sqlite_store.py 가 안다.
    여기는 chunks 를 읽어 (id, 텍스트) 목록으로 만들어 넘길 뿐이다.

    기본은 증분이다. 바뀐 조각만 다시 임베딩한다.
    py -m pipeline.embed --full  로 전량 재구축한다.
    검색은 query.py 를 쓴다.
"""

import sqlite3
import sys

from app.adapters.stores.sqlite_store import chunk_id
from app.core.config import DB_PATH, EMBED_MODEL
from app.features.embedding_sync import sync


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
    full = "--full" in sys.argv
    con = sqlite3.connect(DB_PATH)
    chunks = fetch_chunks(con.cursor())
    if not chunks:
        raise SystemExit("색인할 리뷰가 없습니다. 먼저 chunk.py 를 실행하세요.")

    # ids[i] 와 texts[i] 가 같은 조각을 가리켜야 한다. 같은 목록을 두 번 훑어 만든다.
    ids = [chunk_id(c["purchase_id"], c["chunk_index"]) for c in chunks]
    texts = [c["body"] for c in chunks]

    result = sync(con, "chunk", ids, texts, full=full)

    # 조각 '전체'의 지문은 여기서 남긴다 - retrieve.py 의 check_freshness() 가 이 값을 본다.
    # 저장소는 조각 하나하나의 지문만 알지, chunks 테이블 전체의 지문은 모른다.
    source = f"{len(chunks)}:{sum(c['purchase_id'] for c in chunks)}:{sum(c['n_tokens'] for c in chunks)}"
    con.executemany("INSERT OR REPLACE INTO embedding_meta VALUES (?, ?)",
                    [("count", str(len(chunks))), ("source", source)])
    con.commit()

    print(f"\n{'전량' if full else '증분'} 색인 - 모델 {EMBED_MODEL}")
    print(f"  대상 {len(ids):,}개 / 새로 {result['embedded']:,} "
          f"/ 그대로 {result['skipped']:,} / 지움 {result['deleted']:,}")
    print("검색은 query.py 를 실행하세요.")

    con.close()



if __name__ == "__main__":
    main()
