"""스키마에 실재하는 테이블·컬럼 이름을 읽고 들고 있는 자리.

여기가 general_query 전체의 토대다. 이유는 하나다 —
**테이블 이름과 컬럼 이름은 ? 로 묶을 수 없다.** sqlite 에서 ? 는 '값' 자리에만 들어가고,
식별자 자리에 쓰면 문법 오류가 나거나(FROM ?) 문자열 상수로 조용히 해석된다(SELECT ?).
그래서 식별자는 f-string 에 글자로 박는 수밖에 없고, 박기 전에 실재하는 이름인지 걸러야 한다.

값은 ? 로 묶으면 끝이지만 식별자는 그게 안 되니, 화이트리스트가 유일한 방어선이다.
select / insert / update 가 SQL 을 만들기 전에 전부 여기를 거친다.
(실증은 tests/query_sample.py 의 E-1 ~ E-3 에 있다)
"""
# from functools import lru_cache

from app.core.db import fetch_tuples, QueryError


def get_all_table_names() -> list[str]:
    """
    # Summary
    * 이 DB 에 있는 테이블 이름 전부. 뷰는 빼고 테이블만 준다

    # info
    * sqlite_master 는 sqlite_sequence 같은 내부 테이블도 같이 준다. sqlite_ 로 시작하는 건 뺀다 —
      execute_schema.drop_all() 이 쓰는 조건과 같다
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


def where_clause(table, table_cols, where : dict) -> tuple[str, tuple]:
    """
    # Summary
    * WHERE 절과 거기 들어갈 값을 같이 만든다. where 가 비면 ('', ()) 라 절 자체가 안 붙는다

    # info
    * 값이 list/tuple/set 이면 `IN (?, ?, ...)`, 아니면 `= ?` 다. 부르는 쪽은 dict 하나만 넘기고
      연산자를 안 고른다 — 'pet_id 하나' 와 'pet_id 여럿' 은 같은 조건이고 개수만 다르다
    * 컬럼 이름은 여기서 화이트리스트를 거치고, 값은 전부 ? 로 나간다. IN 도 마찬가지라
      목록 길이만큼 ? 를 찍는다. 값을 글자로 이어붙이면 여기가 그대로 주입 구멍이 된다
    * 빈 목록은 거절한다. sqlite 는 `IN ()` 을 문법 오류로 보고, 설령 받아준대도 '아무것도 안 맞음'
      이라 조용히 0행이 된다 — 부른 쪽이 목록을 못 만든 걸 결과 없음으로 덮는 셈이다
    * ? 개수는 sqlite 한도(3.32+ 기준 32766)를 넘을 수 없다. 몇 만 건을 넣을 자리면 IN 이 아니라
      임시 테이블 조인으로 가야 한다
    * select / select_range / update_query 가 전부 이걸 쓴다. WHERE 를 각자 만들면
      IN 을 지원하는 곳과 안 하는 곳이 갈린다

    # params
    * table: 거절할 때 사유에 담을 테이블 이름
    * table_cols: 그 테이블의 실재 컬럼. 부른 쪽이 이미 읽어둔 걸 그대로 받는다
    * where: {컬럼: 값} 또는 {컬럼: [값, ...]} — AND 로 이어진다

    # return value
    * (' WHERE a = ? AND b IN (?, ?)', (값들...)) — 앞의 공백까지 포함해서 준다
    * ('', ()) : where 가 빔

    # raises
    * QueryError: unknown_column (없는 컬럼) / empty_in (빈 목록)
    """
    if not where:
        return "", ()

    unknown = where.keys() - table_cols
    if unknown:
        raise QueryError("unknown_column", table, sorted(unknown))

    parts, params = [], []
    for col, val in where.items():
        if isinstance(val, (list, tuple, set, frozenset)):
            # set 은 순서가 없어 두 번 돌면 안 된다. ? 개수와 값 순서가 같은 한 벌이어야 한다
            values = tuple(val)
            if not values:
                raise QueryError("empty_in", table, col)
            parts.append(f"{col} IN ({', '.join('?' for _ in values)})")
            params.extend(values)
        else:
            parts.append(f"{col} = ?")
            params.append(val)

    # 조건은 콤마가 아니라 AND 로 잇는다. 콤마로 이으면 조건이 하나일 때만 우연히 돌아간다
    return " WHERE " + " AND ".join(parts), tuple(params)
