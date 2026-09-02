"""쓰기 쿼리 — INSERT.

execute 를 거치니 제약 위반(IntegrityError)이 QueryError('constraint_*') 로 갈아끼워져 올라온다.
그래서 여기서 나오는 QueryError 는 두 갈래다 — 우리가 SQL 을 안 만든 것(500)과 DB 가 거절한 것(400/409).
가르는 기준은 db.QueryError 독스트링에 있다.
"""
from app.core.db import execute, QueryError
from app.repositories.general_query.columns import ColumnMgr


def insert_query(table : str, insert_val : dict) -> int:
    """
    # summary
    * 범용적인 INSERT 쿼리 (한 행)

    # params
    * table: table name
    * insert_val: 넣을 값
        * dict 형태로 k = v, k = v ...
        * 여기 없는 컬럼은 스키마의 기본값으로 채워진다. 기본값도 NOT NULL 도 아니면 DB 가 거절한다

    # return value
    * 새로 생긴 행의 rowid

    # info
    * INTEGER PRIMARY KEY 인 테이블에선 rowid 가 곧 그 PK 값이다. 이 DB 의 테이블은 전부 그 모양이라
      돌려받은 값을 그대로 id 로 쓰면 된다 (WITHOUT ROWID 테이블이 생기면 이 약속이 깨진다)
    * 여러 행을 한 번에 넣는 건 안 받는다. executemany 는 rowcount 만 주고 id 를 안 줘서,
      넣은 뒤 id 가 필요한 쪽이 결국 다시 조회해야 한다

    # raises
    * QueryError: 쿼리를 만들지 못했거나 DB 가 거절했습니다. reason 에 사유가 들어있습니다
    """
    # 넣을 값이 없다. 'INSERT INTO t () VALUES ()' 라는 깨진 SQL 이 된다
    if not insert_val:
        raise QueryError("no_values", table)

    # 컬럼 이름은 ? 로 못 묶어 SQL 에 글자로 들어간다. 만들기 전에 실재 컬럼인지 본다
    cols = ColumnMgr.get_inst().get_col_names(table)
    if not cols:
        raise QueryError("unknown_table", table)

    unknown = insert_val.keys() - cols
    if unknown:
        raise QueryError("unknown_column", table, sorted(unknown))

    names = ", ".join(insert_val)
    # 값 자리는 전부 ? 다. 개수가 컬럼 수와 어긋나면 sqlite 가 실행 전에 잡는다
    marks = ", ".join("?" for _ in insert_val)
    return execute(f"INSERT INTO {table} ({names}) VALUES ({marks})",
                   tuple(insert_val.values()), table).lastrowid
