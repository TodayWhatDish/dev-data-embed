# Last Updated : 2026-09-01

""" VectorStore 계약을 지키는 SQLite 어댑터.
    Protocol 이라 상속은 안 한다.
"""

import sqlite3
import sqlite_vec

def _chunk_id(purchase_id: int, chunk_index: int) -> str:
    """ chunk_vectors의 복합키 (purchase_id, chunk_index)를 
        VectorStore가 기대하는 문자열 id 하나로 합친다."""
    return f"{purchase_id}:{chunk_index}"

def _split_chunk_id(chunk_id:str) -> tuple[int,int]:
    """ 합성 id를 되돌려 원래 복합키로 되돌린다."""
    pass

# 미구현
class SqliteVectorStore:
    def __init__(self, con: sqlite3.Connection):
        self._con = con

    def search(self, kind:str, query_vector, k: int, *,
               only_ids = None, reverse: bool=False) -> list[tuple[str,float]]:
        pass