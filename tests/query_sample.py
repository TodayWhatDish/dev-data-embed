"""
general_query 가 막기로 한 케이스를 한 군데 모아 돌려본다.

막는 자리가 두 층이라 사유도 두 갈래다 —
  * general_query 가 SQL 을 만들기 전에 거절 (unknown_table, unknown_column, no_where ...)
  * DB 가 실행하다 거절 (constraint_*)
둘 다 QueryError 로 올라오지만 **DB 에 갔느냐**가 다르다. 앞쪽이 방어선이고 뒤쪽은 그물이다.

실제 DB(data/pet_reco.db)를 건드리지 않는다. 쓰기는 전부 '반드시 실패하는 값'으로만 하고,
막지 않았을 때 어떻게 되는지는 메모리 DB 를 따로 만들어 본다.
"""
import logging
import sqlite3

from app.app_logger.logger import init_logger
from app.core.db import QueryError, con, fetch_tuples, fetch_tuple_one
from app.repositories.general_query import update_query, update_query_all


logger = logging.getLogger()


def rejects(reason, fn, *args):
    """그 사유로 거절당하는지 본다. 통과했거나 다른 사유면 실패다.

    '실패했다'만 보면 엉뚱한 이유로 막혀도 통과해버린다. reason 까지 봐야 의미가 있다.
    """
    try:
        fn(*args)
    except QueryError as e:
        assert e.reason == reason, f'사유가 다르다: {e.reason} != {reason}'
        logger.info(f'\t{reason:18} <- {e}')
        return
    raise AssertionError(f'거절당해야 하는데 통과했다: {reason}')


def scratch_db() -> sqlite3.Connection:
    """실제 DB 와 무관한 메모리 DB. '안 막으면 어떻게 되는지'를 여기서만 본다."""
    mem = sqlite3.connect(':memory:')
    mem.execute("""CREATE TABLE product_category (product_category_id INTEGER PRIMARY KEY)""")
    mem.execute("""CREATE TABLE product (
                       product_id          INTEGER PRIMARY KEY,
                       product_category_id INTEGER NOT NULL
                           REFERENCES product_category(product_category_id),
                       name                TEXT    NOT NULL,
                       price_krw           INTEGER NOT NULL CHECK (price_krw >= 0))""")
    mem.execute("INSERT INTO product_category VALUES (1)")
    mem.execute("INSERT INTO product VALUES (1, 1, '사료', 1000)")
    return mem


if __name__ == '__main__':
    init_logger('query_sample')

    pid, other = [i for i, in fetch_tuples('SELECT product_id FROM product ORDER BY product_id LIMIT 2')]
    before = fetch_tuple_one('SELECT count(*), sum(price_krw) FROM product')

    # ------------------------------------------------------------------ A
    logger.info('A. SQL 을 만들기 전에 막는다 (DB 에 안 간다)')

    # 테이블 전체 UPDATE 는 사고가 크다. 부른 쪽이 True 를 적어야만 나간다
    rejects('not_verified', update_query_all, 'product', {'price_krw': 1})
    # SET 이 비면 'UPDATE product SET  WHERE ...' 라는 깨진 SQL 이 된다
    rejects('no_values', update_query_all, 'product', {}, True)
    rejects('no_values', update_query, 'product', {}, {'product_id': pid})
    # WHERE 가 비면 조건 없는 UPDATE = 테이블 전체다. update_query 로는 안 받는다
    rejects('no_where', update_query, 'product', {'price_krw': 1}, {})
    # 테이블·컬럼 이름은 ? 로 못 묶어 f-string 에 글자로 박힌다. 박기 전에 ColumnMgr 로 본다
    rejects('unknown_table', update_query, 'no_such_table', {'price_krw': 1}, {'product_id': pid})
    rejects('unknown_column', update_query, 'product', {'no_such_col': 1}, {'product_id': pid})
    rejects('unknown_column', update_query, 'product', {'price_krw': 1}, {'no_such_col': 1})
    # 주입. 키 하나에 SET 절을 통째로 넣는 시도다. E-1 에서 안 막으면 어떻게 되는지 본다
    rejects('unknown_column', update_query, 'product', {'price_krw = 1, name': 'x'}, {'product_id': pid})
    logger.info('#' * 20)

    # ------------------------------------------------------------------ B
    logger.info('B. DB 가 거절한다 (SQL 은 나갔다)')

    # CHECK (price_krw >= 0)
    rejects('constraint_check', update_query, 'product', {'price_krw': -1}, {'product_id': pid})
    # CHECK (is_active IN (0, 1))
    rejects('constraint_check', update_query, 'product', {'is_active': 2}, {'product_id': pid})
    # NOT NULL. 파이썬 None 은 값이라 ? 로 묶여 나가고 DB 가 잡는다
    rejects('constraint_notnull', update_query, 'product', {'name': None}, {'product_id': pid})
    # PK 충돌. SQLITE_CONSTRAINT_PRIMARYKEY 도 unique 로 묶는다 (부른 쪽엔 같은 얘기다)
    rejects('constraint_unique', update_query, 'product', {'product_id': other}, {'product_id': pid})

    # FK 는 sqlite 가 기본으로 안 본다. 켜져 있을 때만 검사한다 - E-4 참고
    fk_on, = con.execute('PRAGMA foreign_keys').fetchone()
    if fk_on:
        rejects('constraint_fk', update_query, 'product',
                {'product_category_id': 999999}, {'product_id': pid})
    else:
        logger.warning('\tPRAGMA foreign_keys = 0 -> constraint_fk 는 지금 도달할 수 없다')
    logger.info('#' * 20)

    # ------------------------------------------------------------------ C
    logger.info('C. 일부러 안 막는다')

    # 조건에 맞는 행이 없는 것은 에러가 아니다. 0 을 돌려주고 부른 쪽이 404 를 정한다
    assert update_query('product', {'price_krw': 1}, {'product_id': -1}) == 0
    logger.info('\t없는 id UPDATE -> 0행, 예외 아님')

    # SQL 에 글자로 박힌 오타는 우리 버그다. QueryError 로 갈아끼우지 않는다 —
    # 'no such table: prodcut' 이 그대로 올라가야 어디가 틀렸는지 바로 보인다
    try:
        fetch_tuples('SELECT * FROM prodcut')
        raise AssertionError('터졌어야 한다')
    except sqlite3.OperationalError as e:
        logger.info(f'\t박힌 오타 -> {type(e).__name__}: {e} (500 이 맞다)')
    logger.info('#' * 20)

    # ------------------------------------------------------------------ D
    logger.info('D. 여기까지 실제 DB 는 그대로여야 한다')
    after = fetch_tuple_one('SELECT count(*), sum(price_krw) FROM product')
    assert after == before, f'DB 가 바뀌었다: {before} -> {after}'
    logger.info(f'\t{before[0]}행 / 합계 {before[1]} 그대로')
    logger.info('#' * 20)

    # ------------------------------------------------------------------ E
    logger.info('E. 안 막으면 어떻게 되는지 (메모리 DB)')
    mem = scratch_db()

    # E-1. 주입 키를 안 거르고 f-string 에 박으면 sqlite 는 군말 없이 실행한다.
    #      A 의 마지막 rejects 가 없으면 여기까지 온다. 에러가 안 나는 게 무서운 점이다
    mem.execute("UPDATE product SET price_krw = 1, name = ? WHERE product_id = 1", ('해킹됨',))
    assert mem.execute('SELECT price_krw, name FROM product').fetchone() == (1, '해킹됨')
    logger.info('\tE-1 주입 성공: price_krw 1000 -> 1, name -> 해킹됨 (예외 없음)')

    # E-2. 식별자 자리엔 ? 를 못 쓴다. 그래서 f-string 말고는 방법이 없고, 그래서 화이트리스트가 필요하다
    for sql in ('SELECT * FROM ?', 'UPDATE ? SET name = ?'):
        try:
            mem.execute(sql, ('product', 'x'))
            raise AssertionError(f'터졌어야 한다: {sql}')
        except sqlite3.OperationalError as e:
            logger.info(f'\tE-2 {sql!r} -> {e}')

    # E-3. 컬럼 자리의 ? 는 조용히 틀린다. 문법 오류도 아니어서 배포된 뒤에나 안다
    assert mem.execute('SELECT ? FROM product', ('name',)).fetchall() == [('name',)]
    logger.info("\tE-3 SELECT ? FROM product -> [('name',)] : 컬럼이 아니라 문자열이다")
    mem.execute("INSERT INTO product VALUES (2, 1, '간식', 500)")
    got = mem.execute('SELECT product_id FROM product ORDER BY ?', ('name',)).fetchall()
    assert got == [(1,), (2,)], got
    logger.info(f'\tE-3 ORDER BY ? -> {got} : 상수 취급이라 정렬이 그냥 안 된다')

    # E-4. FK 는 켜야 본다. 꺼져 있으면 없는 부모를 가리켜도 INSERT 가 통과한다
    mem.execute("INSERT INTO product VALUES (3, 999999, '유령', 100)")
    logger.info('\tE-4 foreign_keys OFF -> 없는 분류 999999 로 INSERT 통과')
    # PRAGMA foreign_keys 는 트랜잭션 안에서 조용히 무시된다. 앞의 INSERT 들이 열어둔 걸 닫고 켠다
    mem.commit()
    mem.execute('PRAGMA foreign_keys = ON')
    try:
        mem.execute("INSERT INTO product VALUES (4, 999999, '유령', 100)")
        raise AssertionError('터졌어야 한다')
    except sqlite3.IntegrityError as e:
        logger.info(f'\tE-4 foreign_keys ON  -> {type(e).__name__}: {e}')
    mem.close()
    logger.info('#' * 20)

    logger.info('ok')
