# Last Updated : 2026-08-31
"""데이터베이스에 닿는 자리를 여기 하나로 모은다."""

import sqlite3
import json
import threading
from app.core.config import DB_PATH, INDEX_FILTER

# 스레드마다 자기 커넥션을 쓴다. 전에는 모듈 전역 커넥션 하나를 check_same_thread=False 로 열어
# 다 같이 썼는데, 라우트가 전부 def(= async 아님)라 FastAPI 가 스레드풀에서 돌린다.
# 같은 커넥션을 여러 스레드가 동시에 execute 하면 sqlite 가 아니라 파이썬 sqlite3 모듈 쪽
# 커넥션 내부 상태가 깨져서 InterfaceError('bad parameter or other API misuse') 가 난다
# (4스레드 동시 SELECT 12,000회 중 1,121회 실패 — 실측은 docs/WORK.md 2026-09-03 §5).
# 스레드당 하나면 그 공유 자체가 없어진다. 커넥션은 닫지 않는다 — 스레드풀 스레드는 프로세스가
# 살아있는 동안 재사용되므로 스레드 수(기본 40)만큼만 열리고, 그게 상한이다.
_local = threading.local()


def get_con() -> sqlite3.Connection:
    """이 스레드 전용 커넥션. 없으면 만들어서 들고 있는다.

    DB 에 닿는 모든 함수가 여기를 거친다. 모듈 전역 con 을 두지 않는 이유는 위 주석에 있다.
    check_same_thread 는 껐던 걸 되돌렸다 — 이제 스레드를 넘어 쓰는 건 버그라서, 막아주는 게 맞다.
    """
    con = getattr(_local, "con", None)
    if con is None:
        con = _local.con = sqlite3.connect(DB_PATH)
    return con


class QueryError(Exception):
    """
    # Summary
    * 쿼리가 거절된 이유를 담아 위층으로 올린다

    # info
    * reason 으로 책임 소재가 갈린다 — 위층이 이걸 보고 HTTP 상태를 정한다
        * constraint_* : DB 가 거절한 것. 들어온 값이 잘못됐다 -> 400/409
        * 그 밖(no_where, unknown_column ...) : 우리가 SQL 을 안 만든 것.
          부른 쪽 코드가 잘못 쓴 거라 서버 버그다 -> 500
    * 사유를 문자열 하나로 뭉개지 않는 이유는, 위층이 문자열을 파싱하게 만들면 안 되기 때문이다

    # params
    * reason: 위 목록 중 하나
    * table: 어느 테이블에서 났는지. 모르면 None
    * detail: 어떤 컬럼이 틀렸는지 등 사람이 볼 부연
    """
    def __init__(self, reason, table=None, detail=None):
        super().__init__(f"{reason}: table={table}, detail={detail}")
        self.reason = reason
        self.table = table
        self.detail = detail


# sqlite 제약 위반 이름 -> reason. 메시지 문자열을 파싱하지 않으려고 errorname 을 쓴다
CONSTRAINT_REASON = {
    'SQLITE_CONSTRAINT_UNIQUE':     'constraint_unique',
    'SQLITE_CONSTRAINT_PRIMARYKEY': 'constraint_unique',
    'SQLITE_CONSTRAINT_CHECK':      'constraint_check',
    'SQLITE_CONSTRAINT_FOREIGNKEY': 'constraint_fk',
    'SQLITE_CONSTRAINT_NOTNULL':    'constraint_notnull',
}


def execute(sql, params=(), table=None) -> sqlite3.Cursor:
    """쓰기 쿼리를 돌리고 커밋한다. 커서를 주니 rowcount / lastrowid 는 부르는 쪽이 골라 쓴다.

    제약 위반(IntegrityError)만 QueryError 로 갈아끼운다. 여기가 sqlite3 예외의 마지막 자리다 —
    get_con().execute 를 직접 부르면 이 변환을 건너뛰니 쓰기는 전부 이걸 통한다.
    잠김·디스크·손상(OperationalError 등)은 안 잡는다. 클라가 어쩔 수 있는 게 아니라 500 이 맞다.
    """
    try:
        con = get_con()
        cur = con.execute(sql, params)
        con.commit()
        return cur
    except sqlite3.IntegrityError as e:
        raise QueryError(CONSTRAINT_REASON.get(getattr(e, 'sqlite_errorname', ''), 'constraint_other'),
                         table, str(e)) from e


def fetch(sql, params=()) -> list[dict]:
    """SELECT 결과를 행마다 dict 로 꺼낸다. k 는 컬럼 이름, v 는 그 칸의 값이다.

    이름에 모양을 안 적은 게 기본이라는 뜻이다 — repositories 가 도메인에 list[dict] 로 넘기기로
    한 그 모양이다. 규약을 어기는 fetch_tuples 쪽이 이름값을 치른다.
    """
    cur = get_con().execute(sql, params)
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_one(sql, params=()) -> dict | None:
    """SELECT 결과의 첫 행만 dict 로 꺼낸다. 없으면 None.

    '없는 id 는 예외가 아니라 None' 이 이 프로젝트의 조회 규약이라, 그걸 한 군데로 모은다.
    부르는 쪽에서 rows[0] if rows else None 을 반복하지 않게.
    """
    rows = fetch(sql, params)
    return rows[0] if rows else None


def fetch_tuples(sql, params=()) -> list[tuple]:
    """SELECT 결과를 행마다 튜플로 꺼낸다. 컬럼 이름은 안 붙는다.

    자리로 꺼내는 거라 SELECT 목록이 바뀌면 조용히 어긋난다. 그래서 기본이 아니고,
    for a, b in ... 처럼 컬럼 두엇을 바로 푸는 자리에서만 쓴다.
    """
    return get_con().execute(sql, params).fetchall()


def fetch_tuple_one(sql, params=()) -> tuple | None:
    """fetch_tuples 의 한 행짜리. 없으면 None.

    fetch_tuples 와 철자가 겹치지 않게 _one 을 붙였다. tuple / tuples 한 글자 차이는 못 본다.
    """
    return get_con().execute(sql, params).fetchone()

def load_vectors(table, key, connection=None):
    """문자로 넣어둔 백터정보를 Numpy 행렬로 숫자화해서 되살리는 함수"""
    import numpy as np

    # 만약 해당 함수를 호출하는 파일에 con접속객체가 있으면 그걸 재활용하고 없으면 새로 만들어서 전달
    active_con = connection if connection is not None else get_con()

    # DB에 가지고온 id값과 벡터 좌표값을 담을 빈 리스트 2개 생성
    ids, rows = [], []

    # 인수로 전달된 테이블에서 ID열과 vector 열을 한 행씩 가져옴
    for row_id, vector in active_con.execute(f"SELECT {key}, vector FROM {table}"):
        ids.append(row_id)
        # 리스트에 따옴표가 붙어있어서 통짜로 문자화되어 있는 데이터를 json객체형태로 변경
        rows.append(json.loads(vector))

    # 객체안쪽에 있는 vector안쪽의 좌표값을 다시 숫자형태로 변경
    return ids, np.array(rows, dtype="float32")
