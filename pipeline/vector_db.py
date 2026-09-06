import sqlite3

import sqlite_vec

from app.core.config import DB_PATH, EMBED_MODEL

def connect(): # DB연결하고 VEC 확장을 추가해서 벡터거리계산하는 함수를 쓸수있는 커넥션을 만들었음
    # check_same_thread=False : FastAPI sync 엔드포인트는 요청마다 스레드풀의 다른 스레드에서 도는데
    # lifespan에서 만든 커넥션 하나를 여러 요청이 재사용하므로 필요함 (읽기 전용 쿼리만 하므로 안전)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.enable_load_extension(True) # 확장로딩이 기본값 False라 문을 열어줌
    sqlite_vec.load(con) # sqlite에 없는 함수를 vec.load로 con에 추가해준다 
    con.enable_load_extension(False) # 보안을 위해 문을 다시 닫아줌
    return con

# 이 친구가 먼저 벡터DB를 저장해, 그 다음 사용자가 자연어로 요청시 search가 저장된 데이터를 읽어서 반환해
def save_vectors(con, chunks, vectors, dim, source): # 안전비교작업.chunk_vectors 만들고 값넣음
    # con, chunks, vectors, dim, source 전부 build_index.py로 부터 준비되어 옵니다
    # chunk_vectors 테이블 만듬. 벡터를 바이너리로 저장. 바이너리 = SQLite blob
    # 1개 벡터를 float32로 저장 = 4바이트 384개 × 4바이트 = 1,536바이트
    cur = con.cursor()

    if not cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"
        # sqlite_master 테이블은 전체 DB를 찾는 것. WHERE절대로 뽑을 것. SELECT name = chunks
    ).fetchone(): # chunks 있다면 튜플로 반환함
        raise ValueError("chunks 테이블이 없습니다. storage.save_chunks 를 먼저 실행하세요.")

    if len(chunks) != len(vectors): 
        raise ValueError(f"조각 {len(chunks)}개와 벡터 {len(vectors)}개의 수가 다릅니다.")
        # 아래 zip할때 개수 안맞으면 잘라버리니까 chunks, vectors 개수가 안맞으면 에러시킴
    cur.execute("DROP TABLE IF EXISTS chunk_vectors") 
    # 1. chunks 테이블 purchase_id, chunk_index 가 있습니다
    # 2. CSV 데이터 수정삭제시 옛 벡터를 남겨두면 새 텍스트랑 안맞는 벡터가 섞여 검색오염
    # 3. CSV 원본에서 매번 전체를 다시 만드는 배치재구축 구조임 같이 재구축해야 정합성맞음

    cur.execute(""" 
    CREATE TABLE chunk_vectors (
        purchase_id INTEGER NOT NULL,
        chunk_index INTEGER NOT NULL,
        vector      BLOB,        
        PRIMARY KEY (purchase_id, chunk_index),
        FOREIGN KEY (purchase_id, chunk_index) REFERENCES chunks (purchase_id, chunk_index)
    ) """) 
    # BLOB 숫자 그대로 압축 roaw bytes
    # chunk_vectors 테이블 여기서 만듬
    # PK FK 따로따로 복합키를 설정함 chunks도 복합키임 연결하려면 FK도 똑같이 두 컬럼을 묶어야 함
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS embedding_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    # meta 위아래 두개는 단지 메모장임
    # 벡터를 검색 가능하게 했을 당시에 모델등등 상태를 아래 INSERT 통해서 추가되는 것일 뿐
    # 누적은 안 돼.

    cur.executemany(
        "INSERT INTO chunk_vectors VALUES (?, ?, ?)",
        [
            (chunk["purchase_id"], chunk["chunk_index"], sqlite_vec.serialize_float32(vec))
            for chunk, vec in zip(chunks, vectors) # zip 어떤벡터가 어떤조각인지 연결시켜줌.
        ],  # for문 각각 짝지어져서 purchase_id | chunk_index | vectors 한행씩 들어감.
    )
    cur.executemany(
        "INSERT OR REPLACE INTO embedding_meta VALUES (?, ?)",
        [
            ("model", EMBED_MODEL),
            ("dim", str(dim)),
            ("count", str(len(chunks))),
            ("source", source),
        ],
    )
    con.commit() # 이때 DB 확정저장임 커밋해야함.
