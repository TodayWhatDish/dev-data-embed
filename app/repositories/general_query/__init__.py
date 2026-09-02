"""테이블 이름과 컬럼 이름을 인자로 받아 SQL 을 만들어주는 범용 쿼리 묶음.

한 파일이던 걸 넷으로 나눴다. 나눈 선은 '무슨 SQL 을 만드느냐' 다 —
  * columns : 스키마에 실재하는 테이블·컬럼 (아래 셋이 전부 여기를 거친다)
  * select  : SELECT — select_all, select, select_range
  * insert  : INSERT — insert_query
  * update  : UPDATE — update_query, update_query_all

여기서 재수출하니 부르는 쪽은 나뉜 걸 몰라도 된다:
    from app.repositories.general_query import update_query
경로가 그대로라 기존 호출부는 한 줄도 안 바뀐다.

주의 — 이 파일의 재수출이 패키지 속성을 덮어쓴다. general_query.select 는 select 모듈이 아니라
select 함수다. 모듈을 직접 잡아야 하면 from ...general_query.select import ... 로 가져와라.
"""
from app.repositories.general_query.columns import get_all_table_names, ColumnMgr
from app.repositories.general_query.select import select_all, select, select_range
from app.repositories.general_query.insert import insert_query
from app.repositories.general_query.update import update_query, update_query_all

__all__ = [
    'get_all_table_names', 'ColumnMgr',
    'select_all', 'select', 'select_range',
    'insert_query',
    'update_query', 'update_query_all',
]
