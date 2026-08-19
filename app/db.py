# LastUpdated : 2026-08-19

import sqlite3
from app.config import DB_PATH
con = sqlite3.connect(DB_PATH)

def query(sql,params=(),fetch=0):
    '''
    행 정보 반환 함수
    '''
    if fetch == 1:
        return con.execute(sql,params).fetchone()
    else:
        return con.execute(sql,params).fetchall()

def dicts(sql,params=()):
    cur = con.execute(sql,params)
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns,row)) for row in cur.fetchall()]

