import logging

from app.app_logger.logger import init_logger
from app.core.db import QueryError, fetch, fetch_tuples
from app.repositories.general_query import (ColumnMgr, get_all_table_names,
                                            update_query)


logger = logging.getLogger()


def rejects(reason, fn, *args):
    """그 사유로 거절당하는지 본다. 통과했거나 다른 사유면 실패다.

    '실패했다'만 보면 엉뚱한 이유로 막혀도 통과해버린다. reason 까지 봐야 의미가 있다.
    """
    try:
        fn(*args)
    except QueryError as e:
        assert e.reason == reason, f'사유가 다르다: {e.reason} != {reason}'
        return
    raise AssertionError(f'거절당해야 하는데 통과했다: {reason}')


if __name__ == '__main__':
    init_logger('test_column_mgr')
    mgr = ColumnMgr.get_inst()

    logger.info('1. reload() - 테이블 목록부터 다시 읽는다')
    mgr.reload()

    tables = get_all_table_names()
    assert set(mgr._col_names) == set(tables), set(mgr._col_names) ^ set(tables)
    logger.info(f'\t테이블 {len(tables)}개 적재')

    # 뷰는 담기지 않는다. get_all_table_names() 가 type = 'table' 로 거르기 때문이고,
    # 쓰기(update_query)는 뷰에 못 하니 이게 맞다. 뷰를 select 대상으로 삼는 날 여기가 먼저 깨진다.
    # views = [name for name, in fetch_tuples("SELECT name FROM sqlite_master WHERE type = 'view'")]
    # assert not (set(views) & set(mgr._col_names)), views
    # logger.info(f'\t뷰 {len(views)}개는 제외: {views}')
    logger.info('#' * 20)

    logger.info('2. 캐시한 컬럼 이름으로 실제 SELECT 가 되는지')
    # 이 검사가 본론이다. 캐시가 DB 와 어긋나면 update_query 가 통과시킨 컬럼이
    # f-string 으로 박힌 뒤 'no such column' 으로 터진다. 그걸 여기서 먼저 잡는다.
    for table in tables:
        cols = mgr.get_col_names(table)
        assert cols, f'{table}: 컬럼이 비었다'
        rows = fetch(f"SELECT {', '.join(sorted(cols))} FROM {table} LIMIT 1")
        # 빈 테이블이면 돌려줄 행이 없다. SELECT 가 안 터진 것만으로 컬럼 이름은 증명된다
        if rows:
            assert rows[0].keys() == cols, f'{table}: {rows[0].keys()} != {cols}'
    logger.info(f'\t{len(tables)}개 테이블 전부 조회됨')
    logger.info('#' * 20)

    logger.info('3. 캐시에 없는 이름은 DB 에 가기 전에 막힌다')
    rejects('unknown_table', update_query, 'no_such_table', {'name': 'x'}, {'product_id': 1})
    rejects('unknown_column', update_query, 'product', {'no_such_col': 1}, {'product_id': 1})
    # ? 로 못 묶는 자리라 f-string 에 박힌다. 화이트리스트가 유일한 방어선인 자리다
    rejects('unknown_column', update_query, 'product', {'price_krw = 1, name': 'x'}, {'product_id': 1})
    logger.info('#' * 20)

    logger.info('4. 스키마가 안 바뀌었으면 reload() 결과도 같아야 한다')
    before = dict(mgr._col_names)
    mgr.reload()
    assert mgr._col_names == before, '두 번 읽었는데 달라졌다'
    logger.info('#' * 20)

    logger.info('ok')
