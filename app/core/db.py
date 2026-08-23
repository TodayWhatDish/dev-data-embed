"""데이터베이스에 닿는 자리를 여기 하나로 모은다.

다른 파일은 전부 이렇게 쓴다 ─
    from app.core.db import query, one, dicts
"""

import sqlite3
from app.core.config import DB_PATH
con = sqlite3.connect(DB_PATH)


def query(sql, params=()):
    """여러 줄을 꺼낸다. 튜플의 목록이 온다."""
    return con.execute(sql, params).fetchall()


def one(sql, params=()):
    """한 줄만 꺼낸다. 없으면 None 이 온다."""
    return con.execute(sql, params).fetchone()


def dicts(sql, params=()):
    """컬럼 이름이 붙은 딕셔너리 목록으로 꺼낸다."""
    cur = con.execute(sql, params)
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]
