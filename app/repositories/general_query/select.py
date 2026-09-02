"""읽기 쿼리. SELECT 한 종류를 조건·페이징·정렬로 나눠 담았다.

읽기라 execute 를 안 거치고 fetch 로 바로 간다 — 제약 위반이 날 일이 없어서 QueryError 는
전부 'SQL 을 만들기 전에 거절' 쪽이다. 식별자를 화이트리스트로 거르는 이유는 columns 참고.
"""
from app.core.db import fetch, QueryError
from app.repositories.general_query.columns import ColumnMgr


def _order_clause(table, cols, order_by) -> str:
    """
    # Summary
    * ORDER BY 절을 만든다. order_by 가 비면 빈 문자열이라 절 자체가 안 붙는다

    # info
    * 컬럼 이름도 ASC/DESC 도 ? 로 못 묶어 SQL 에 글자로 들어간다. 그래서 컬럼은 cols 로 거르고
      방향은 두 글자 중 하나인지 본다. 방향을 안 거르면 넘어온 문자열이 그대로 SQL 이 된다
    * 적은 순서대로 앞에서부터 비교한다. 앞 키에서 승부가 나면 뒤 키는 아예 안 본다 —
      유일한 컬럼(PK 등)을 앞에 두면 그 뒤는 전부 죽은 절이 된다. 동점 끊기는 맨 뒤에 붙인다
    * where / update_val 과 달리 dict 가 아니라 list 로 받는다. 순서가 결과를 바꾸는 인자라
      순서가 의미를 갖는다는 걸 모양에 드러내야 한다. dict 는 매핑으로 읽혀서 그게 안 보이고,
      {**a, **b} 나 컴프리헨션으로 만들면 순서가 조용히 뒤집힌다
    * 방향은 생략할 수 없다. sqlite 기본이 ASC 지만, 적혀 있어야 읽는 쪽이 안 헷갈린다
    * UPDATE / DELETE 는 이걸 안 쓴다. sqlite 는 기본 빌드에서 그 자리의 ORDER BY 를 안 받는다

    # params
    * table: 거절할 때 사유에 담을 테이블 이름
    * cols: 그 테이블의 실재 컬럼. 부른 쪽이 이미 읽어둔 걸 그대로 받는다
    * order_by: [(컬럼, 'ASC' | 'DESC'), ...] — 방향은 대소문자를 안 가린다

    # return value
    * ' ORDER BY a ASC, b DESC' 또는 '' — 앞의 공백까지 포함해서 준다

    # raises
    * QueryError: unknown_column (없는 컬럼) / bad_order (방향이 틀렸거나 컬럼이 겹침)
    """
    if not order_by:
        return ""

    unknown = {col for col, _ in order_by} - cols
    if unknown:
        raise QueryError("unknown_column", table, sorted(unknown))

    # dict 는 키가 겹치면 알아서 하나로 합쳐졌지만 list 는 그냥 통과한다.
    # 'ORDER BY name ASC, name DESC' 는 문법은 맞고 뒤가 무시된다 — 조용히 틀리니 여기서 잡는다
    seen = [col for col, _ in order_by]
    if len(seen) != len(set(seen)):
        raise QueryError("bad_order", table, f"중복 컬럼: {seen}")

    parts = []
    for col, direction in order_by:
        way = str(direction).upper()
        if way not in ("ASC", "DESC"):
            raise QueryError("bad_order", table, f"{col}={direction}")
        parts.append(f"{col} {way}")

    return " ORDER BY " + ", ".join(parts)

def select_all(table : str, order_by : list[tuple] | None = None) -> list[dict]:
    """
    # summary
    * 범용적인 TABLE 전체 SELECT 쿼리

    # params
    * table: table name
    * order_by: 정렬 (선택)
        * [(컬럼, 'ASC' | 'DESC'), ...] 형태. 적은 순서가 곧 정렬 우선순위다

    # return value
    * list[dict] : 행마다 dict. k 는 컬럼 이름, v 는 그 칸의 값
    * []         : 행이 없음 (에러가 아니다)

    # info
    * 전량 스캔이다. 행이 몇 만이 되면 부르는 쪽이 select_range 로 갈아타야 한다
    * 조건이 없는 건 여기서만 허용한다 — select 는 WHERE 를 안 받으면 거절한다.
      '전체를 읽는다' 는 뜻이 이름에 적혀 있어야 실수로 전량 스캔하는 일이 없다

    # raises
    * QueryError: 쿼리를 만들지 못했습니다. reason 에 사유가 들어있습니다
    """
    # 테이블 이름은 ? 로 못 묶어 SQL 에 글자로 들어간다. 만들기 전에 실재하는 테이블인지 본다
    cols = ColumnMgr.get_inst().get_col_names(table)
    if not cols:
        raise QueryError("unknown_table", table)

    return fetch(f"SELECT * FROM {table}{_order_clause(table, cols, order_by)}")

def select(table : str, where : dict, order_by : list[tuple] | None = None) -> list[dict]:
    """
    # summary
    * 범용적인 SELECT 쿼리

    # params
    * table: table name
    * where: WHERE 절 조건문
        * dict 형태로 k = v, k = v ... (AND 로 이어진다)
    * order_by: 정렬 (선택)
        * [(컬럼, 'ASC' | 'DESC'), ...] 형태. 적은 순서가 곧 정렬 우선순위다

    # return value
    * list[dict] : 행마다 dict. k 는 컬럼 이름, v 는 그 칸의 값
    * []         : 조건에 맞는 행이 없음 (에러가 아니다 — 부른 쪽이 404 를 정한다)

    # info
    * 조건은 = 만 된다. IN, LIKE, 범위 비교가 필요하면 그 테이블 전용 함수를 따로 판다
    * where 가 비면 거절한다. SQL 은 안 깨지지만 그건 select_all 이고,
      빈 dict 가 넘어온 건 부른 쪽이 조건을 못 만든 것에 가깝다

    # raises
    * QueryError: 쿼리를 만들지 못했습니다. reason 에 사유가 들어있습니다
    """
    if not where:
        raise QueryError("no_where", table)

    cols = ColumnMgr.get_inst().get_col_names(table)
    if not cols:
        raise QueryError("unknown_table", table)

    unknown = where.keys() - cols
    if unknown:
        raise QueryError("unknown_column", table, sorted(unknown))

    # 조건은 콤마가 아니라 AND 로 잇는다. 콤마로 이으면 조건이 하나일 때만 우연히 돌아간다
    wheres = " AND ".join(f"{k} = ?" for k in where)
    orders = _order_clause(table, cols, order_by)
    return fetch(f"SELECT * FROM {table} WHERE {wheres}{orders}", tuple(where.values()))

def select_range(table: str, where : dict, size : int, start_offset : int | None = 0,
                 order_by : list[tuple] | None = None) -> list[dict]:
    """
    # summary
    * 범용적인 SELECT 쿼리 (페이징)

    # params
    * table: table name
    * where: WHERE 절 조건문
        * dict 형태로 k = v, k = v ... (AND 로 이어진다)
        * 비어 있어도 된다. 그때는 조건 없이 size 만큼만 끊어 읽는다
    * size: 한 번에 가져올 행 수. 1 이상이어야 한다
    * start_offset: 건너뛸 행 수. None 이면 0
    * order_by: 정렬 (선택이지만 페이징에선 사실상 필수 — 아래 info)
        * [(컬럼, 'ASC' | 'DESC'), ...] 형태. 적은 순서가 곧 정렬 우선순위다

    # return value
    * list[dict] : 행마다 dict. 최대 size 행
    * []         : 그 구간에 행이 없음 (에러가 아니다 — 마지막 페이지 다음이면 정상이다)

    # info
    * where 를 안 받는 select 와 달리 여기선 빈 dict 를 허용한다. LIMIT 이 이미 결과를 묶고 있고,
      조건 없이 페이지로 훑는 건 흔한 요구다 (products.find_page 가 그 모양이다)
    * size 를 검사하는 이유 — sqlite 는 LIMIT -1 을 '제한 없음' 으로 읽는다.
      음수가 그냥 지나가면 페이지를 달라고 해놓고 테이블을 통째로 받는다
    * order_by 를 비우면 sqlite 가 순서를 보장하지 않는다. 그런데 OFFSET 은 '앞에서 몇 개'를
      건너뛰는 거라, 순서가 흔들리면 페이지를 넘기는 사이 같은 행이 두 번 나오거나 빠진다.
      1 페이지만 볼 게 아니면 정렬을 걸어라
    * 정렬 컬럼이 안 겹치는 값(PK 같은)이 아니면 같은 값끼리의 순서는 또 보장되지 않는다.
      [('price_krw', 'DESC'), ('product_id', 'ASC')] 처럼 **맨 뒤에** PK 를 붙여 동점을 끊는다.
      앞에 두면 거기서 승부가 나버려 뒤의 price_krw 가 죽는다
    * LIMIT / OFFSET 은 식별자가 아니라 값이라 ? 로 묶을 수 있다 (컬럼 이름과 다른 점이다)

    # raises
    * QueryError: 쿼리를 만들지 못했습니다. reason 에 사유가 들어있습니다
    """
    if size < 1:
        raise QueryError("bad_range", table, f"size={size}")

    offset = start_offset or 0
    if offset < 0:
        raise QueryError("bad_range", table, f"start_offset={start_offset}")

    cols = ColumnMgr.get_inst().get_col_names(table)
    if not cols:
        raise QueryError("unknown_table", table)

    unknown = where.keys() - cols
    if unknown:
        raise QueryError("unknown_column", table, sorted(unknown))

    # WHERE 는 없을 수 있다. 없으면 절 자체를 빼야 'WHERE' 만 남은 깨진 SQL 이 안 된다
    wheres = " AND ".join(f"{k} = ?" for k in where)
    clause = f" WHERE {wheres}" if where else ""
    # ORDER BY 는 LIMIT 보다 앞이다. 순서를 바꾸면 문법 오류다
    orders = _order_clause(table, cols, order_by)

    # WHERE 값이 먼저, size / offset 이 나중 - ? 자리 순서와 같아야 한다.
    # 정렬은 글자로 박혀 있어 ? 자리를 차지하지 않는다
    return fetch(f"SELECT * FROM {table}{clause}{orders} LIMIT ? OFFSET ?",
                 (*where.values(), size, offset))
