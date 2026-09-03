"""동시성에서 무너지는 축이 무엇인지 가른다 — 문장 수도 스캔량도 아니고 **파이썬으로 꺼낸 행 수**다.

master_join_workers.py 에서 B 그룹(29행)만 유별나게 무너지는 걸 보고 만든 자리다.
A(1행)는 32스레드에서 x0.86 인데 B 는 4스레드에서 이미 x0.19 였고, B1/B2/B3 가 똑같이 무너져서
캐시도 general_query 도 아니었다. 남은 변수가 반환 행 수뿐이라 여기서 따로 잰다.

두 판으로 나눠 재는 이유:
  1. LIMIT 만 바꾸기 — 반환 행이 늘면 무너지는지 본다. 다만 스캔량도 같이 늘어서 원인을 못 가린다
  2. 스캔량 고정 — 같은 2039행을 훑으면서 반환 행만 바꾼다. 여기서 원인이 갈린다

기대하는 그림: sqlite 안에서 끝나는 일(집계)은 GIL 이 풀린 채 돌아 코어 수만큼 병렬로 빨라지고,
행을 파이썬으로 꺼내는 일은 행마다 GIL 을 잡아 직렬화된다.
결론과 숫자는 docs/WORK.md 2026-09-03 §9.

    python -m tests.bench.rows
"""
import logging

from app.app_logger.logger import init_logger

init_logger('bench_rows')
logging.getLogger().setLevel(logging.WARNING)     # 벤치 중 INFO 로그가 측정값에 섞이지 않게

from app.core.db import fetch_tuple_one, fetch_tuples
from app.features.metric.sqlbench import throughput_fn

THREADS = (1, 4, 8)


def q(sql):
    """인자 없는 호출로 만든다. throughput_fn 이 그 모양만 받는다"""
    return lambda: fetch_tuples(sql)


if __name__ == '__main__':
    n, = fetch_tuple_one('SELECT count(*) FROM review')

    print()
    print('1. LIMIT 만 바꾼다 - 반환 행이 늘면 무너지는가 (스캔량도 같이 늘어 원인은 못 가림)')
    throughput_fn({f'{i:>4}행': q(f'SELECT product_id FROM product LIMIT {i}')
                   for i in (1, 3, 10, 30, 100)}, threads=THREADS)

    print()
    print(f'2. 스캔량을 {n} 으로 고정하고 반환 행만 바꾼다 - 여기서 원인이 갈린다')
    got = throughput_fn({
        'count(*)            반환   1행': q('SELECT count(*) FROM review'),
        'sum(length(body))   반환   1행': q('SELECT sum(length(body)), avg(rating) FROM review'),
        f'purchase_id         반환{n}행': q('SELECT purchase_id FROM review'),
        f'purchase_id + body  반환{n}행': q('SELECT purchase_id, body FROM review'),
    }, threads=THREADS)

    for name, _rate, failed in got:
        assert not failed, f'{name} 이 동시 실행에서 {failed}회 터졌다'

    print()
    print('3. 실제 요청 경로. 위가 합성 쿼리였다면 이건 라우트가 진짜 부르는 함수다')
    from app.api.lifespan import load_domain_cache, load_schema_cache
    from app.repositories import pet as pet_repo
    from app.repositories import users as users_repo
    load_domain_cache()
    load_schema_cache()
    rows = len(users_repo.list_users())
    throughput_fn({f'list_users        {rows}행 (GET /api/customers)': users_repo.list_users,
                   'find_pets_by_user   3행 (프로필 조회)': lambda: pet_repo.find_pets_by_user(1)},
                  threads=THREADS)

    print()
    print('  집계(1행 반환)는 스레드를 늘리면 빨라지고, 전행 반환은 무너진다.')
    print('  일이 sqlite 안에서 끝나면 GIL 이 풀린 채 병렬로 돌기 때문이다.')
