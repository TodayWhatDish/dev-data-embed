# Last Updated : 2026-09-01

""" VectorStore 계약을 지키는 SQLite 어댑터.
    Protocol 이라 상속은 안 한다.
"""

import sqlite3
import sqlite_vec

def chunk_id(purchase_id: int, chunk_index: int) -> str:
    """ chunk_vectors의 복합키 (purchase_id, chunk_index)를 
        VectorStore가 기대하는 문자열 id 하나로 합친다."""
    return f"{purchase_id}:{chunk_index}"

def _split_chunk_id(chunk_id: str) -> tuple[int, int]:
    """ 합성 id를 되돌려 원래 복합키로 되돌린다."""
    purchase_id, chunk_index = chunk_id.split(":")
    return int(purchase_id), int(chunk_index)


# kind -> (벡터 테이블, 원본 테이블). 지금은 chunk 하나뿐이지만
# port.py의 VectorStore 계약이 kind를 문자열로 받으므로 표로 둔다.
TABLES = {
    "chunk": ("chunk_vectors", "chunks"),
}

class SqliteVectorStore:
    def __init__(self, con: sqlite3.Connection):
        self._con = con

    def recreate(self, kind: str, *, dim: int, model: str, payload_columns=None) -> None:
        table, parent = TABLES[kind]
        cur = self._con.cursor()
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(f"""
        CREATE TABLE {table} (
            purchase_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            vector      BLOB NOT NULL,
            source_hash TEXT NOT NULL,
            PRIMARY KEY (purchase_id, chunk_index),
            FOREIGN KEY (purchase_id, chunk_index) REFERENCES {parent} (purchase_id, chunk_index)
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS embedding_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        cur.executemany(
            "INSERT OR REPLACE INTO embedding_meta VALUES (?, ?)",
            [("model", model), ("dim", str(dim))],
        )
        self._con.commit()

    def search(self, kind:str, query_vector, k: int, *,
               only_ids = None, reverse: bool=False) -> list[tuple[str,float]]:
        pass

    def hashes(self, kind: str, *, ids=None) -> dict[str, str]:
        table, _parent = TABLES[kind]
        cur = self._con.cursor()
        try:
            rows = cur.execute(
                f"SELECT purchase_id, chunk_index, source_hash FROM {table}"
            ).fetchall()
        except sqlite3.OperationalError:
            return {}  # 테이블이 아직 없다 = 아는 지문이 없다

        result = {chunk_id(pid, idx): h for pid, idx, h in rows}
        if ids is None:
            return result
        wanted = set(ids)
        return {k: v for k, v in result.items() if k in wanted}
    
    def upsert(self, kind, ids, vectors, *, model, hashes, payloads=None) -> None:
        table, _parent = TABLES[kind]
        cur = self._con.cursor()
        rows = [
            (*_split_chunk_id(item_id), sqlite_vec.serialize_float32(vec), h)
            for item_id, vec, h in zip(ids, vectors, hashes)
        ]
        cur.executemany(
            f"INSERT OR REPLACE INTO {table} "
            "(purchase_id, chunk_index, vector, source_hash) VALUES (?, ?, ?, ?)",
            rows,
        )
        cur.execute("INSERT OR REPLACE INTO embedding_meta VALUES ('model', ?)", (model,))
        self._con.commit()

    def delete(self, kind, ids) -> None:
        if not ids:
            return
        table, _parent = TABLES[kind]
        cur = self._con.cursor()
        pairs = [_split_chunk_id(item_id) for item_id in ids]
        cur.executemany(
            f"DELETE FROM {table} WHERE purchase_id = ? AND chunk_index = ?", pairs
        )
        self._con.commit()
