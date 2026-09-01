import sqlite3

import sqlite_vec

from app.core.config import DB_PATH, EMBED_MODEL, EMBED_NORMALIZE, QUERY_PREFIX
from app.core.embedder import get_embeddings
from app.features.retrieve import check_freshness

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

def search(con, query, where = "1=1", params: tuple = (), top_k: int = 3):
    """입력된 자연어 질문 하나를 받아서, DB에 저장된 리뷰 조각들 중 질문과 의미가 가장 비슷한 것을 최대 top_k개 뽑아준다.
    질문 -> 벡터 -> DB안 벡터들과 거리 비교 -> 정렬 -> 중복 제거 -> 최종 까지의 프로세스를 거친다."""

    for line in check_freshness(con):
        print(f"[경고] {line}")

    model = get_embeddings()
    q_vec = sqlite_vec.serialize_float32(
    model.encode([f"{QUERY_PREFIX}{query}"], normalize_embeddings=EMBED_NORMALIZE,
                     show_progress_bar=False)[0]
    )

    # 1 con : 사용자검색하면 FastAPI 엔드포인트가 요청받고 엔드포인트 함수 동작함. 
    # 2 con이 DB에 SQL날려서 정보를 가지고 con통로로 다시 보내줌
    # query : FastAPI 엔드포인트가 요청으로 받은 사용자가 타이핑한 자연어를 얘가 받음.
    
    # rows는 chunk 하나 당 한줄을 의미한다.
    rows = con.execute(f"""
        SELECT v.purchase_id, pu.product_id, c.body, vec_distance_cosine(v.vector, ?) AS distance
        FROM chunk_vectors AS v
        JOIN chunks AS c ON c.purchase_id = v.purchase_id AND c.chunk_index = v.chunk_index
        JOIN purchase AS pu ON pu.purchase_id = v.purchase_id
        JOIN review AS r ON r.purchase_id = pu.purchase_id
        WHERE {where}
        ORDER BY distance
    """, (q_vec, *params)).fetchall()

    # rows 사용자 자연어랑 비교할 것들을 쿼리문생성
    # rows 구매건 번호, 리뷰 조각들, 검색어 거리 
    # rows 리뷰조각들 여러개 일수가 있습니다 아래서 제일 비슷한 조각 하나만 남겨줌.

    best = {}
    for purchase_id, product_id, body, distance in rows:
        if purchase_id not in best or distance < best[purchase_id][2]: 
            best[purchase_id] = (product_id, body, distance)
    # best 구매건마다 사용자 검색어랑 비슷한 조각들을 담음.
    # best 구매건ID 중복으로 들어온다면 distance 코사인을 비교해 유사도 높은 것만 남김

    # 상품이 겹치면 제일 유사도 높은 리뷰 하나만 남긴다 - 후보 3개가 같은 상품 리뷰로 채워지는 것을 방지 (중복제거)
    best_per_product = {}
    for purchase_id, (product_id, body, distance) in best.items():
        if product_id not in best_per_product or distance < best_per_product[product_id][-1]:
            best_per_product[product_id] = (purchase_id, body, distance)

    ranked = sorted(best_per_product.values(), key=lambda item: item[-1])[:top_k] 
    return [(purchase_id, 1 - distance, body) for purchase_id, body, distance in ranked]

    # 반환시 1 빼기 각 코사인거리를 빼주니까 유사도가 높은 순대로 나옴 유사도 높은것 3개만 남김
    # 형태도 튜플로 다시 묶어서 리스트로 반환