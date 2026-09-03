"""쓰기 쿼리 — UPDATE.

여기가 이 패키지에서 가장 위험한 자리다. 조건을 빠뜨린 UPDATE 는 문법이 멀쩡한 채로
테이블 전체를 갈아버린다. 그래서 두 함수로 갈라뒀다 —
  * update_query     : WHERE 를 반드시 받는다. 없으면 no_where 로 거절
  * update_query_all : 전체 UPDATE 를 하겠다고 부른 쪽이 True 를 적어야만 나간다
'전체를 고친다' 는 뜻이 함수 이름과 인자에 드러나 있어야 실수로 도달하지 않는다.
"""
from app.core.db import execute, QueryError
from app.repositories.general_query.columns import ColumnMgr


def update_query_all(table : str, update_val : dict, is_verified : bool | None = False):
    """
        # summary
        * 범용적인 TABLE 전체 UPDATE 쿼리

        # params
        * table: table name
        * update_val: 업데이트 값
            * dict 형태로 k = v, k = v ...
        * is_verfied : 사용자 확인 **(주의)**
            * 해당 쿼리는 테이블 전체가 업데이트이기 때문에, 항상 쿼리를 수행한 당사자가 True를 인자로 넣어야합니다.
            * 인자가 없으면 수행되지 않고, QueryError 를 냅니다.

        # return value
        * 0 < : 업데이트 된 행의 갯수
        * 0   : 업데이트 된 행이 없음

        # raises
        * QueryError: 쿼리를 만들지 못했거나 DB 가 거절했습니다. reason 에 사유가 들어있습니다
    """
    if not is_verified:
        raise QueryError("not_verified", table)

    if not update_val:
        raise QueryError("no_values", table)

    # 컬럼 이름은 ? 로 못 묶어 SQL 에 글자로 들어간다. 만들기 전에 실재 컬럼인지 본다
    cols = ColumnMgr.get_inst().get_col_names(table)
    if not cols:
        raise QueryError("unknown_table", table)

    unknown = update_val.keys() - cols
    if unknown:
        raise QueryError("unknown_column", table, sorted(unknown))

    sets = ", ".join(f"{k} = ?" for k in update_val)
    # execute 는 파라미터를 시퀀스 하나로 받는다. 풀어서 넘기면 두 번째 인자로 들어가 터진다
    return execute(f"UPDATE {table} SET {sets}", tuple(update_val.values()), table).rowcount

def update_query(table : str, update_val : dict, where : dict):
    """
    # summary
    * 범용적인 UPDATE 쿼리

    # params
    * table: table name
    * update_val: 업데이트 값
        * dict 형태로 k = v, k = v ...
    * where: WHERE 절 조건문
        * dict형태로 k = v, k = v ...

    # return value
    * 0 < : 업데이트 된 행의 갯수
    * 0   : 업데이트 된 행이 없음 (조건에 맞는 행이 없다 — 에러가 아니다)

    # raises
    * QueryError: 쿼리를 만들지 못했거나 DB 가 거절했습니다. reason 에 사유가 들어있습니다
    """

    # 업데이트 할 정보가 없다
    if not update_val:
        raise QueryError("no_values", table)

    # WHERE 가 비면 SQL 이 깨진다. 조건 없는 UPDATE 는 테이블 전체라 여기서 받지 않는다
    if not where:
        raise QueryError("no_where", table)

    cols = ColumnMgr.get_inst().get_col_names(table)
    if not cols:
        raise QueryError("unknown_table", table)

    unknown = (update_val.keys() | where.keys()) - cols
    if unknown:
        raise QueryError("unknown_column", table, sorted(unknown))

    sets = ", ".join(f"{k} = ?" for k in update_val)
    # 조건은 콤마가 아니라 AND 로 잇는다. 콤마로 이으면 조건이 하나일 때만 우연히 돌아간다
    wheres = " AND ".join(f"{k} = ?" for k in where)
    # SET 값이 먼저, WHERE 값이 나중 - ? 자리 순서와 같아야 한다
    return execute(f"UPDATE {table} SET {sets} WHERE {wheres}",
                   (*update_val.values(), *where.values()), table).rowcount
