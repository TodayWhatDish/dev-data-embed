from app.core.db import dicts, query, con

def select_all(table : str):
    pass

def select(table : str, where : dict):
    pass

def select_range(table: str, where : dict, size : int, start_offset : int | None = 0):
    pass

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
            * 인자가 없으면 수행되지 않고, -1을 리턴합니다.

        # return value
        * 0 < : 업데이트 된 행의 갯수
        * 0   : 업데이트 된 행이 없음
        * -1  : 사용자가 확인을 하지 않아여, 쿼리를 수행하지 않습니다.
    """
    if not is_verified:
        return -1
    sets = ", ".join(f"{k} = ?" for k in update_val)
    # execute 는 파라미터를 시퀀스 하나로 받는다. 풀어서 넘기면 두 번째 인자로 들어가 터진다
    cursor = con.execute(f"UPDATE {table} SET {sets}"
    , tuple(update_val.values()))
    con.commit()
    return cursor.rowcount

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
    * 0   : 업데이트 된 행이 없음
    * -1  : 업데이트할 열 정보가 없어, 쿼리를 수행하지 않습니다.
    """

    # 업데이트 할 정보가 없다면 -1을 리턴
    if not update_val:
        return -1

    sets = ", ".join(f"{k} = ?" for k in update_val)
    # 조건은 콤마가 아니라 AND 로 잇는다. 콤마로 이으면 조건이 하나일 때만 우연히 돌아간다
    wheres = " AND ".join(f"{k} = ?" for k in where)
    # SET 값이 먼저, WHERE 값이 나중 - ? 자리 순서와 같아야 한다
    cursor = con.execute(f"UPDATE {table} SET {sets} WHERE {wheres}"
    , (*update_val.values(), *where.values())
                         )
    con.commit()
    return cursor.rowcount
