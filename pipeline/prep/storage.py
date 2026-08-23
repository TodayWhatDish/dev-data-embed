# Last Updated : 2026-08-23

""" 조각과 벡터를 DB에 적재한다.

    무엇을 넣을지 알게된다 (함수 인자 chunks, vectors로 이미 완성되어 넘어오기 때문)
    그게 어떻게 만들어졌는지는 모른다. 즉, 자르거나 임베딩하는 법은 해당 문서에 존재하지 않는다.

"""

import json
import sqlite3
from app.core.config import EMBED_MODEL

def save_chunks(con: sqlite3.Connection, chunks : list[dict]):
    """조각을 chunks 테이블에 넣으며, 재실행 시 통째로 다시 만든다."""
    pass

def save_vectors(con: sqlite3.Connection, chunks : list[dict], vectors, dim, source : str):
    """chunk_vecttors 테이블을 만들고 벡터에 적재한다. 이때 chunks는 미리 저장되어 있어야 한다."""
    pass

