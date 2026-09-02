# from functools import lru_cache

from app.core.db import fetch, fetch_tuples, con, execute, QueryError

def get_all_table_names() -> list[str]:
    """
    # Summary
    * 이 DB 에 있는 테이블 이름 전부. 뷰는 빼고 테이블만 준다

    # info
    * sqlite_master 는 sqlite_sequence 같은 내부 테이블도 같이 준다. sqlite_ 로 시작하는 건 뺀다 —
      execute_schema.drop_all() 이 쓰는 조건과 같다
    * 테이블 이름은 ? 로 못 묶어 SQL 에 글자로 들어간다. 실재하는지 거르는 데 쓴다
    * 이름순으로 준다. 부를 때마다 순서가 달라지면 비교하는 쪽이 곤란하다
    """
    return [name for (name,) in fetch_tuples(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name;")]

def _get_col_names(table_name) -> set[str]:
    """
    # Summary
    * 그 테이블에 실재하는 컬럼 이름. 없는 테이블이면 빈 set 이라 테이블명 검사도 같이 된다

    # info
    * 컬럼·테이블 이름은 ? 로 묶을 수 없어 SQL 에 글자로 들어간다. 그래서 SQL 을 만들기 전에
      이걸로 걸러야 한다 (general_query) — 값만 바인딩하는 걸로는 부족하다
    """
    return {row[0] for row in fetch_tuples('SELECT name FROM pragma_table_info(?);', (table_name,))}

# lru_cache 판. 아래 명시적 dict 판과 동작이 같아서 지금은 안 쓴다
# @lru_cache(maxsize=None)
# def get_col_names_cached(table_name) -> frozenset[str]:
#     return frozenset(get_col_names(table_name))

class ColumnMgr:
    """
    # Summary
    * 테이블별 컬럼 이름을 메모리에 들고 있는 싱글턴

    # info
    * k: 테이블 이름, v: 그 테이블의 컬럼 이름들(frozenset)
    * 처음 get_inst() 할 때 테이블 목록을 읽고 테이블마다 컬럼을 한 번씩 담는다.
      그 뒤로는 DB 를 보지 않는다 — 스키마는 서버가 떠 있는 동안 안 바뀐다
    * 도메인의 XxxMgr 과 달리 init_from_db() 로 먹여주지 않고 스스로 채운다.
      general_query 는 파이프라인 스크립트에서도 불려서 기동 절차를 안 거치는 경로가 있다
    """
    _instance = None

    def __init__(self):
        self.reload()

    @classmethod
    def get_inst(cls): #싱글턴 패턴을 위한
        if cls._instance == None:
            cls._instance = ColumnMgr()
        return cls._instance

    def reload(self):
        """
        # Summary
        * 테이블 목록부터 다시 읽어서 전부 새로 담는다

        # info
        * 기동 시 1회 적재가 이걸로 이뤄진다. 서비스 중엔 스키마가 안 바뀌니 다시 부를 일이 없고,
          create_schema() 로 갈아엎은 뒤나 자체검증에서만 쓴다
        * 비우기만 하면 모든 테이블이 '없는 테이블' 이 되어 쿼리가 전부 막힌다. 그래서 비우지 않고 채운다
        """
        self._col_names = {name: frozenset(_get_col_names(name))
                           for name in get_all_table_names()}

    def get_col_names(self, table_name) -> frozenset[str]:
        """
        # Summary
        * 그 테이블의 컬럼 이름. 담아둔 것만 보고 DB 는 보지 않는다

        # info
        * 없는 테이블이면 빈 frozenset 이라, 이걸로 테이블명 검사까지 같이 된다
        * frozenset 이라 받아간 쪽이 고쳐도 캐시가 오염되지 않는다

        # params
        * table_name: 컬럼을 알고 싶은 테이블 이름
        """

        # frozenset: const set

        return self._col_names.get(table_name, frozenset())

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
