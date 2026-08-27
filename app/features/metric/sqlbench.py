# Last Updated: 2026-08-24
"""
SQL 변형 비교 — 같은 결과인지 확인하고, 빠른 순으로 줄세운다.

범용 함수 타이밍은 stdlib timeit 을 쓴다. 이 모듈은 timeit 이 안 해주는 것만 한다:
변형들의 결과가 같은지 대조하는 것(compare), 그리고 임의의 블록 재기(elapsed_time).

    py src/sqlbench.py      # self-check
"""
import statistics
import time


class elapsed_time:
    """블록이 걸린 시간을 재는 컨텍스트 매니저.

        with elapsed_time('제품 적재'):
            load(...)                       # -> "제품 적재   123.45 ms"

        with elapsed_time(quiet=True) as t:
            rows = con.execute(sql).fetchall()
        if t.ms > 100: ...                  # 값만 쓰고 출력은 안 함

    __exit__ 는 예외가 나도 돌기 때문에 실패한 작업이 몇 ms 먹었는지도 남는다.
        
    """

    def __init__(self, label='', quiet=False):
        self.label, self.quiet, self.ms = label, quiet, None

    def __enter__(self):
        self._t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = (time.perf_counter() - self._t) * 1000
        if not self.quiet:
            print(f'{self.label:26} {self.ms:8.2f} ms')
        return False

"""
compare 함수는 같은 결과 db 쿼리에 대해서 성능을 비교하는 함수
 - 이 위치가 아니라서, 삭제 또는 위치 변경 필요
"""

def compare(con, variants, params=(), n=50, plan=True):
    """variants: {이름: SQL}. 첫 번째를 기준으로 나머지 결과가 같은지 확인한 뒤 시간을 잰다.

    결과가 다르면 AssertionError 로 멈춘다.
        - 같은 결과여야 성능 비교하는데, 의미 있다.
    평균은 첫 실행의 캐시 미스 한 번에 통째로 끌려간다.
    """

    rows = {name: con.execute(sql, params).fetchall() for name, sql in variants.items()}
    base_name, base = next(iter(rows.items()))
    for name, got in rows.items(): #결과가 같은지 확인
        assert sorted(got) == sorted(base), \
            f'{name} 결과가 {base_name} 와 다르다: {len(got)}행 vs {len(base)}행'

    out = []
    for name, sql in variants.items():
        ts = []
        for _ in range(n): # n번 실행
            with elapsed_time(quiet=True) as t:
                con.execute(sql, params).fetchall()
            ts.append(t.ms)
        out.append((statistics.median(ts), name, sql)) #중앙 값을 기록
    out.sort()

    best = out[0][0]
    print(f'rows={len(base)}  n={n}  (중앙값)')
    for ms, name, _ in out: # 결과 출력
        print(f'  {name:26} {ms:7.2f} ms   x{ms / best:.2f}')
    if plan:
        print(f'\n[{out[0][1]} 실행계획]')
        for r in con.execute('EXPLAIN QUERY PLAN ' + out[0][2], params):
            print('  ', r[-1])
    return [(name, ms) for ms, name, _ in out]


def _demo():
    import sqlite3
    con = sqlite3.connect(':memory:')
    con.executescript("""
        CREATE TABLE t(id INTEGER PRIMARY KEY, g INT);
        CREATE TABLE u(id INTEGER PRIMARY KEY, t_id INT, v INT);
        CREATE INDEX idx_u_t ON u(t_id);
    """)
    con.executemany('INSERT INTO t VALUES(?,?)', [(i, i % 10) for i in range(1, 2001)])
    con.executemany('INSERT INTO u VALUES(?,?,?)', [(i, i % 2000 + 1, i) for i in range(1, 20001)])

    ranked = compare(con, {
        'IN 서브쿼리':  'SELECT id FROM t WHERE g = ?1 AND id IN (SELECT t_id FROM u WHERE v > 19000)',
        'EXISTS 상관':  'SELECT id FROM t WHERE g = ?1 AND EXISTS (SELECT 1 FROM u WHERE u.t_id = t.id AND u.v > 19000)',
    }, params=(3,), n=30)
    assert len(ranked) == 2 and ranked[0][1] <= ranked[1][1], '정렬이 빠른 순이 아니다'

    with elapsed_time(quiet=True) as t:
        time.sleep(0.02)
    assert 15 < t.ms < 100, f'timed 가 이상하다: {t.ms}'

    try:                                    # 예외를 삼키지 않는지
        with elapsed_time(quiet=True):
            raise ValueError('boom') #일부로 예외를 발생시킨다
    except ValueError:
        pass
    else:
        raise AssertionError('timed 가 예외를 삼켰다')# 98에서 발생 시킨 예외를 100에서 못잡으면 에러 던지기

    # 결과가 다르면 반드시 멈춘다 - 이 가드가 이 모듈의 존재 이유다
    try:
        compare(con, {'a': 'SELECT id FROM t WHERE g = 1', 'b': 'SELECT id FROM t WHERE g = 2'}, plan=False)
    except AssertionError:
        print('\nok - 결과 불일치를 잡는다')
    else:
        raise AssertionError('결과가 다른데 통과했다')


if __name__ == '__main__':
    _demo()
