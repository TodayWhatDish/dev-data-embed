"""master_join.py 의 변형들을 **스레드를 띄워** 동시 처리량으로 다시 잰다.

master_join.py 는 한 호출이 몇 ms 인지(지연)를 쟀다. 그건 혼자 쓸 때 얘기다. API 는 라우트가 전부
`def`(= async 아님)라 FastAPI 가 동시 요청을 스레드풀에서 돌리니, 여기서 보는 건 둘이다:

  1. 스레드를 늘리면 처리량이 느는가
  2. 늘려도 안 터지는가 - 커넥션이 스레드마다 따로여야 한다 (app/core/db.py 의 get_con)

**재는 함수는 master_join 에서 import 한다.** 새로 짜면 두 파일이 서로 다른 걸 재게 되고,
결과가 같은지 대조하는 것도 master_join 의 compare_fn 이 이미 했다.

지연에서 나온 결론은 '조인이냐 캐시냐' 가 아니라 '문장이 몇 개냐' 였다 (문장 하나 31.8us 대
조인 1.2us). 그게 동시에 두들길 때도 유지되는지가 이 파일의 질문이다.

    python -m tests.bench.master_join_workers

py(3.14) 는 fastapi 가 없어서 못 돈다. python(3.12) 으로 돌린다.
"""
from app.core.db import fetch_tuple_one
from app.features.metric.sqlbench import throughput_fn
from tests.bench.master_join import (a_cached, a_cached_raw, a_join, b_cached, b_cached_raw,
                                     b_join, c_cached, c_cached_one, c_cached_raw,
                                     c_join_subquery, c_join_two_selects, load_domain_cache,
                                     load_schema_cache, norm)

THREADS = (1, 3, 4, 5, 6, 8, 12, 14, 16, 20, 32)
SECONDS = 0.5           # 칸이 (변형 x 스레드수) 개라 길게 잡으면 한 판이 몇 분이 된다


def run(title, variants):
    print()
    print(title)
    for name, _rate, failed in throughput_fn(variants, threads=THREADS, seconds=SECONDS):
        # 동시성 버그는 느려지는 게 아니라 예외로 나온다. 하나라도 있으면 위 숫자는 볼 것도 없다
        assert not failed, f'{name} 이 동시 실행에서 {failed}회 터졌다'


if __name__ == '__main__':
    load_domain_cache()
    load_schema_cache()

    typical_pet, = fetch_tuple_one(
        'SELECT pet_id FROM pet_allergy GROUP BY pet_id HAVING count(*) = 3 LIMIT 1')
    heavy_pet, heavy_n = fetch_tuple_one(
        'SELECT pet_id, count(*) FROM pet_allergy GROUP BY pet_id ORDER BY 2 DESC LIMIT 1')
    user_id, pet_n = fetch_tuple_one(
        'SELECT user_id, count(*) FROM pet WHERE inactive_at IS NULL'
        ' GROUP BY user_id ORDER BY 2 DESC LIMIT 1')

    run(f'A. 축종 이름 하나 (pet {typical_pet}) - 전부 1문장이라 조인/캐시만 갈린다',
        {'A1 조인': lambda: a_join(typical_pet),
         'A2 캐시': lambda: a_cached(typical_pet),
         'A3 캐시 raw': lambda: a_cached_raw(typical_pet)})

    run(f'B. 알레르겐 이름 {heavy_n}개 (pet {heavy_pet}) - 캐시 조회가 행 수만큼 늘어 제일 불리하다',
        {'B1 조인': lambda: b_join(heavy_pet),
         'B2 캐시': lambda: b_cached(heavy_pet),
         'B3 캐시 raw': lambda: b_cached_raw(heavy_pet)})

    run(f'C. 펫 목록 + 알레르기 (user {user_id}, 펫 {pet_n}마리) - 1문장 둘 vs 2문장 셋',
        {'C1 조인 1문장': lambda: c_join_subquery(user_id),
         'C4 캐시 1문장': lambda: c_cached_one(user_id),
         'C2 조인 2문장': lambda: c_join_two_selects(user_id),
         'C3 캐시 2문장': lambda: c_cached(user_id),
         'C3r 캐시 raw 2문장': lambda: c_cached_raw(user_id)})

    print()
    print('ok - 실패 0')
