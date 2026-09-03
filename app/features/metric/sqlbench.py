# Last Updated: 2026-08-24
"""
SQL 변형 비교 — 같은 결과인지 확인하고, 빠른 순으로 줄세운다.

범용 함수 타이밍은 stdlib timeit 을 쓴다. 이 모듈은 timeit 이 안 해주는 것만 한다:
변형들의 결과가 같은지 대조하는 것(compare), 그리고 임의의 블록 재기(elapsed_time).

    py src/sqlbench.py      # self-check
"""
import statistics
import threading
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


def compare_fn(variants, n=50, key=None):
    """variants: {이름: 인자 없는 함수}. compare 의 함수판 — SQL 문자열이 아니라 호출을 잰다.

    같은 값을 주는지 먼저 보고 시간을 잰다. 결과가 다르면 AssertionError 로 멈춘다.
    SQL 한 방으로 안 끝나는 구현(SELECT 여러 번 + 메모리 조회)은 문자열로 못 넘기니 이쪽을 쓴다.
    실행계획은 안 찍는다 — 변형마다 쿼리가 0개일 수도, 여러 개일 수도 있어서 하나로 못 고른다.

    * key: 결과 비교 전에 씌울 정규화 함수. 모양이 다른 두 구현(콤마 문자열 vs 리스트)을
      맞춰볼 때만 쓴다. 시간 측정에는 안 들어간다 — 정규화 비용은 구현의 비용이 아니다
    """
    got = {name: fn() for name, fn in variants.items()}
    base_name, base = next(iter(got.items()))
    for name, val in got.items():
        left, right = (key(val), key(base)) if key else (val, base)
        assert left == right, f'{name} 결과가 {base_name} 와 다르다: {left} != {right}'

    out = []
    for name, fn in variants.items():
        ts = []
        for _ in range(n):
            with elapsed_time(quiet=True) as t:
                fn()
            ts.append(t.ms)
        out.append((statistics.median(ts), name))
    out.sort()

    best = out[0][0]
    print(f'  n={n}  (중앙값)')
    for ms, name in out:
        print(f'    {name:32} {ms:8.4f} ms   x{ms / best:.2f}')
    return [(name, ms) for ms, name in out]


def throughput_fn(variants, threads=(1, 4, 8), seconds=0.6):
    """variants: {이름: 인자 없는 함수}. 스레드 수를 올려가며 **초당 처리 건수**를 잰다.

    compare_fn 이 '한 번에 얼마나 걸리나' 라면 이건 '동시에 얼마나 받아내나' 다. 둘이 다른 이유는,
    한 호출이 빨라도 공유 자원(여기선 DB 파일과 커넥션)을 오래 쥐면 동시 처리량은 안 오르기 때문이다.

    실패도 같이 센다. 동시성 버그는 느려지는 게 아니라 **예외로** 나타난다 —
    예전 공유 커넥션이 InterfaceError 를 9% 냈던 게 그 예다(docs/WORK.md 2026-09-03 §5).
    0 이 아니면 숫자는 볼 것도 없으니 그 자리에 실패 수를 찍는다.

    * threads: 재볼 스레드 수들. 1 을 넣어야 배수를 볼 기준이 생긴다
    * seconds: 한 칸마다 도는 시간. 짧게 여러 칸 도는 게 길게 한 칸 도는 것보다 비교에 낫다
    """
    def run(fn, n):
        stop = time.perf_counter() + seconds
        # 락을 안 건다. append 는 GIL 아래서 원자적이고 counts 는 스레드마다 자기 칸만 만진다.
        # 걸면 초당 수만 번 두들기는 락 경합이 측정값에 섞인다 - 재려는 게 그건 아니다
        counts, errors = [0] * n, []
        def work(i):
            while time.perf_counter() < stop:
                try:
                    fn()
                    counts[i] += 1
                except Exception as e:              # noqa: BLE001 - 무슨 예외든 실패다
                    errors.append(f'{type(e).__name__}: {e}')
        workers = [threading.Thread(target=work, args=(i,)) for i in range(n)]
        started = time.perf_counter()
        for t in workers:
            t.start()
        for t in workers:
            t.join()
        return sum(counts) / (time.perf_counter() - started), errors

    # 1건 = fn() 한 번. 숫자는 스레드별이 아니라 **전 스레드 합계**다 - 스레드를 늘려도
    # 합계가 안 늘면 그게 '안 늘었다' 는 뜻이고, 스레드별로 찍으면 그 사실이 안 보인다
    print(f'  스레드당 {seconds}초 (fn() 호출 수 / 초, 전 스레드 합계 / 1스레드 대비)')
    print('    ' + ' ' * 26 + ''.join(f'{n:>9}스레드' for n in threads))
    out = []
    for name, fn in variants.items():
        cells, base, failed = [], None, 0
        for n in threads:
            rate, errors = run(fn, n)
            failed += len(errors)
            if errors:
                cells.append(f'{"실패 " + str(len(errors)):>15}')
                continue
            base = base or rate
            cells.append(f'{rate:11,.0f}/s x{rate / base:.2f}')
        print(f'    {name:26}' + ''.join(cells))
        out.append((name, base, failed))
    return out


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

    ranked = compare_fn({
        'sum(list)':   lambda: sum([i for i in range(2000)]),
        'sum(range)':  lambda: sum(range(2000)),
    }, n=30)
    assert len(ranked) == 2 and ranked[0][1] <= ranked[1][1], 'compare_fn 정렬이 빠른 순이 아니다'

    # key 로 모양을 맞추면 같은 결과로 본다 (콤마 문자열 vs 리스트)
    compare_fn({'문자열': lambda: 'a,b', '리스트': lambda: ['b', 'a']},
               n=3, key=lambda v: sorted(v.split(',') if isinstance(v, str) else v))
    try:
        compare_fn({'a': lambda: 1, 'b': lambda: 2}, n=3)
    except AssertionError:
        print('ok - compare_fn 도 결과 불일치를 잡는다')
    else:
        raise AssertionError('결과가 다른데 통과했다')

    ranked = throughput_fn({'sum(range)': lambda: sum(range(500))}, threads=(1, 2), seconds=0.1)
    assert ranked[0][2] == 0, '예외가 없는데 실패로 셌다'

    def boom():
        raise ValueError('boom')
    assert throughput_fn({'터지는 것': boom}, threads=(1,), seconds=0.05)[0][2] > 0,         'throughput_fn 이 실패를 안 세고 있다'

    # 결과가 다르면 반드시 멈춘다 - 이 가드가 이 모듈의 존재 이유다
    try:
        compare(con, {'a': 'SELECT id FROM t WHERE g = 1', 'b': 'SELECT id FROM t WHERE g = 2'}, plan=False)
    except AssertionError:
        print('\nok - 결과 불일치를 잡는다')
    else:
        raise AssertionError('결과가 다른데 통과했다')


if __name__ == '__main__':
    _demo()
