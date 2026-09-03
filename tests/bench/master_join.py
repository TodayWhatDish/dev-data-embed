"""마스터 테이블 조인 vs 싱글턴 캐시 조회 — 어느 쪽이 빠른지 실측한다.

우리 조회의 조인은 대부분 마스터 테이블(animal_category, allergen) 조인이다. 그 마스터는
기동 때 CommonMgr 이 메모리에 통째로 들고 있으니, 이름을 붙이는 일은 DB 없이도 된다.
그러면 조인을 걷어내고 id 만 SELECT 해서 메모리에서 이름을 찾는 게 나은가? 를 재는 자리다.

**바꾸는 축이 둘이라 따로 잰다.** 안 그러면 뭐가 이겼는지 모른다:
  * 이름 붙이기  : JOIN 마스터        vs 캐시 조회
  * 관계 읽기    : 상관 서브쿼리 1방  vs SELECT 두 번 (IN 으로 부모 id 여럿)
  * SQL 만들기   : 글자로 박힌 SQL   vs general_query (컬럼 화이트리스트 + f-string 조립)
C 그룹이 C1 -> C2 -> C3 로 한 축씩만 바꾼다. C1~C2 차이가 관계 읽기, C2~C3 차이가 이름 붙이기다.
C4 는 캐시를 쓰면서 쿼리는 한 방인 판이다 — **C1 과 맞붙일 짝은 C3 가 아니라 C4 다.**
C3 는 쿼리를 한 번 더 치므로, 그 차이를 캐시 탓으로 읽으면 틀린다 (A/B 는 처음부터 1방 대 1방이다).
'raw' 가 붙은 변형은 캐시는 쓰되 SQL 은 글자로 박은 것이다 — 캐시가 느린 게 캐시 탓인지
general_query 조립 탓인지는 이걸 빼놓으면 못 가린다.

측정 대상은 '결과가 같은 두 구현' 이다. compare_fn 이 먼저 결과를 대조하고, 다르면 멈춘다.

    py -m tests.bench.master_join
"""
import logging

from app.app_logger.logger import init_logger

init_logger('bench_master_join')
# 벤치는 같은 쿼리를 수백 번 돌린다. repositories 의 INFO 로그가 그대로 파일에 쌓이면
# 로그 쓰는 시간이 측정값에 섞인다 - 재는 동안은 경고 위로만 남긴다
logging.getLogger().setLevel(logging.WARNING)

from app.api.lifespan import load_domain_cache, load_schema_cache
from app.core.db import fetch, fetch_tuple_one, fetch_tuples
from app.domain.common import CommonMgr
from app.features.metric.sqlbench import compare_fn
from app.repositories import pet as pet_repo
from app.repositories.general_query import select

PET_COLS = ['pet_id', 'name', 'animal_category_id', 'size', 'inactive_at']


# ---------------------------------------------------------------- A. 축종 하나 붙이기
def a_join(pet_id):
    """지금 구현. pet 1행에 animal_category 를 조인해 이름을 가져온다"""
    return pet_repo.find_category_and_size(pet_id)

def a_cached(pet_id):
    """id 만 읽고 이름은 메모리에서 찾는다. 조인이 사라진 자리에 dict 조회가 들어간다"""
    rows = select('pet', {'pet_id': pet_id}, cols=['animal_category_id', 'size'])
    if not rows:
        return None
    row = rows[0]
    return (CommonMgr.get_inst().get_animal_category(row['animal_category_id'])['name_ko'],
            row['size'])

def a_cached_raw(pet_id):
    """캐시는 그대로 쓰고 SQL 만 글자로 박는다. a_cached 와의 차이가 general_query 조립 비용이다"""
    row = fetch_tuple_one('SELECT animal_category_id, size FROM pet WHERE pet_id = ?', (pet_id,))
    if row is None:
        return None
    return (CommonMgr.get_inst().get_animal_category(row[0])['name_ko'], row[1])


# ---------------------------------------------------------------- B. 알레르겐 이름 N 개
def b_join(pet_id):
    """지금 구현. pet_allergy 에 allergen 을 조인해 이름을 가져온다"""
    return sorted(pet_repo.find_allergen_names(pet_id))

def b_cached(pet_id):
    """관계 테이블에서 id 만 읽고 이름은 전부 메모리에서. 행이 늘수록 조회 횟수도 는다"""
    allergen = CommonMgr.get_inst().get_allergen
    return sorted(allergen(row['allergen_id'])['name_ko']
                  for row in select('pet_allergy', {'pet_id': pet_id}, cols=['allergen_id']))

def b_cached_raw(pet_id):
    """B 의 raw 판. 관계 테이블에서 id 만 글자 SQL 로 읽고 이름은 메모리에서"""
    allergen = CommonMgr.get_inst().get_allergen
    return sorted(allergen(aid)['name_ko'] for (aid,) in fetch_tuples(
        'SELECT allergen_id FROM pet_allergy WHERE pet_id = ?', (pet_id,)))


# ---------------------------------------------------------------- C. 펫 목록 + 알레르기
def c_join_subquery(user_id):
    """지금 구현. 축종은 조인, 알레르기는 상관 서브쿼리로 콤마 문자열 한 칸"""
    return pet_repo.find_pets_by_user(user_id)

def c_join_two_selects(user_id):
    """축종은 그대로 조인. 알레르기만 두 번째 SELECT 로 뺀다 (C1 과의 차이 = 관계 읽는 방식)"""
    pets = fetch("""
        SELECT p.pet_id, p.name, ac.name_ko AS animal_category, p.size
          FROM pet AS p
          JOIN animal_category AS ac ON ac.animal_category_id = p.animal_category_id
         WHERE p.user_id = ? AND p.inactive_at IS NULL
         ORDER BY p.pet_id
    """, (user_id,))
    return _attach(pets, fetch(
        "SELECT pa.pet_id, al.name_ko FROM pet_allergy AS pa "
        "JOIN allergen AS al ON al.allergen_id = pa.allergen_id "
        f"WHERE pa.pet_id IN ({', '.join('?' for _ in pets)})",
        tuple(p['pet_id'] for p in pets)) if pets else [])

def c_cached(user_id):
    """조인이 하나도 없다. pet 을 읽고, 관계를 IN 으로 한 번 더 읽고, 이름은 전부 메모리에서

    inactive_at IS NULL 은 general_query 가 못 만든다 (IS NULL 은 = ? 가 아니다).
    한 사용자의 펫은 많아야 서너 마리라 전부 읽고 파이썬에서 거른다 — 여기 비용은 그 서너 행이다
    """
    cmgr = CommonMgr.get_inst()
    pets = [{'pet_id': row['pet_id'], 'name': row['name'],
             'animal_category': cmgr.get_animal_category(row['animal_category_id'])['name_ko'],
             'size': row['size']}
            for row in select('pet', {'user_id': user_id}, [('pet_id', 'ASC')], PET_COLS)
            if row['inactive_at'] is None]
    if not pets:
        return []

    return _attach(pets, [
        {'pet_id': row['pet_id'], 'name_ko': cmgr.get_allergen(row['allergen_id'])['name_ko']}
        for row in select('pet_allergy', {'pet_id': [p['pet_id'] for p in pets]},
                          cols=['pet_id', 'allergen_id'])])

def c_cached_raw(user_id):
    """C3 의 raw 판. 조인도 general_query 도 없이 SELECT 두 번 + 캐시"""
    cmgr = CommonMgr.get_inst()
    pets = [{'pet_id': pid, 'name': name,
             'animal_category': cmgr.get_animal_category(acid)['name_ko'], 'size': size}
            for pid, name, acid, size in fetch_tuples(
                'SELECT pet_id, name, animal_category_id, size FROM pet '
                'WHERE user_id = ? AND inactive_at IS NULL ORDER BY pet_id', (user_id,))]
    if not pets:
        return []

    ids = tuple(p['pet_id'] for p in pets)
    return _attach(pets, [
        {'pet_id': pid, 'name_ko': cmgr.get_allergen(aid)['name_ko']}
        for pid, aid in fetch_tuples(
            f"SELECT pet_id, allergen_id FROM pet_allergy WHERE pet_id IN ({', '.join('?' * len(ids))})", ids)])

def c_cached_one(user_id):
    """마스터 조인이 하나도 없는 채로 **한 방**. 상관 서브쿼리는 이름 대신 id 만 뽑는다

    C3 와 캐시를 쓰는 건 같고 쿼리 횟수만 1번이다. C1 과는 쿼리 횟수가 같고 이름 붙이는 방법만
    다르다 — 캐시 쪽을 조인과 같은 조건(1문장)에 놓고 재는 자리가 여기다.
    C1/C3 만 있으면 'SELECT 를 한 번 더 친 값' 을 '캐시가 느리다' 로 잘못 읽는다
    """
    cmgr = CommonMgr.get_inst()
    return [{'pet_id': pid, 'name': name,
             'animal_category': cmgr.get_animal_category(acid)['name_ko'],
             'size': size,
             'allergies': [cmgr.get_allergen(int(i))['name_ko'] for i in ids.split(',')] if ids else []}
            for pid, name, acid, size, ids in fetch_tuples("""
                SELECT p.pet_id, p.name, p.animal_category_id, p.size,
                       (SELECT GROUP_CONCAT(pa.allergen_id)
                          FROM pet_allergy AS pa WHERE pa.pet_id = p.pet_id)
                  FROM pet AS p
                 WHERE p.user_id = ? AND p.inactive_at IS NULL
                 ORDER BY p.pet_id""", (user_id,))]

def _attach(pets, allergy_rows):
    """{pet_id: [이름...]} 으로 묶어 각 펫에 붙인다. C2 / C3 가 같이 쓴다"""
    grouped = {}
    for row in allergy_rows:
        grouped.setdefault(row['pet_id'], []).append(row['name_ko'])
    for pet in pets:
        pet['allergies'] = grouped.get(pet['pet_id'], [])
    return pets

def norm(rows):
    """C1 은 콤마 문자열, C2/C3 는 리스트다. 비교 전에만 모양을 맞춘다 (측정에는 안 들어간다)"""
    out = []
    for row in rows:
        got = row.get('allergies')
        out.append({**row, 'allergies': sorted(got.split(',') if isinstance(got, str) else got or [])})
    return out


if __name__ == '__main__':
    load_domain_cache()
    load_schema_cache()

    N = 300
    # 알레르기가 3개(중앙값)인 펫과 29개(최다)인 펫. 캐시 조회 횟수가 관계 행 수만큼 늘어나므로
    # 최다 쪽이 캐시에 제일 불리하다 - 거기서도 이기면 어디서든 이긴다
    typical_pet, = fetch_tuple_one(
        'SELECT pet_id FROM pet_allergy GROUP BY pet_id HAVING count(*) = 3 LIMIT 1')
    heavy_pet, heavy_n = fetch_tuple_one(
        'SELECT pet_id, count(*) FROM pet_allergy GROUP BY pet_id ORDER BY 2 DESC LIMIT 1')
    user_id, pet_n = fetch_tuple_one(
        'SELECT user_id, count(*)' \
        ' FROM pet' \
        ' WHERE inactive_at IS NULL ' \
        ' GROUP BY user_id ORDER BY 2 DESC LIMIT 1')

    print(f'\nA. 축종 이름 하나 (pet {typical_pet})')
    compare_fn({'JOIN 마스터': lambda: a_join(typical_pet),
                'SELECT + 캐시': lambda: a_cached(typical_pet),
                'raw SELECT + 캐시': lambda: a_cached_raw(typical_pet)}, n=N)

    for pet_id, cnt in ((typical_pet, 3), (heavy_pet, heavy_n)):
        print(f'\nB. 알레르겐 이름 {cnt}개 (pet {pet_id})')
        compare_fn({'JOIN 마스터': lambda: b_join(pet_id),
                    'SELECT + 캐시': lambda: b_cached(pet_id),
                    'raw SELECT + 캐시': lambda: b_cached_raw(pet_id)}, n=N)

    print(f'\nC. 펫 목록 + 알레르기 (user {user_id}, 펫 {pet_n}마리)')
    compare_fn({'C1 조인+상관서브쿼리': lambda: c_join_subquery(user_id),
                'C4 캐시+상관서브쿼리': lambda: c_cached_one(user_id),
                'C2 조인+SELECT 2번': lambda: c_join_two_selects(user_id),
                'C3 캐시+SELECT 2번': lambda: c_cached(user_id),
                'C3r 캐시+raw SELECT 2번': lambda: c_cached_raw(user_id)}, n=N, key=norm)

"""
# test 1
A. 축종 이름 하나 (pet 80)
  n=300  (중앙값)
    JOIN 마스터                           0.0253 ms   x1.00
    raw SELECT + 캐시                    0.0256 ms   x1.01
    SELECT + 캐시                        0.0306 ms   x1.21

B. 알레르겐 이름 3개 (pet 80)
  n=300  (중앙값)
    JOIN 마스터                           0.0272 ms   x1.00
    raw SELECT + 캐시                    0.0276 ms   x1.01
    SELECT + 캐시                        0.0335 ms   x1.23

B. 알레르겐 이름 29개 (pet 66)
  n=300  (중앙값)
    raw SELECT + 캐시                    0.0395 ms   x1.00
    JOIN 마스터                           0.0405 ms   x1.03
    SELECT + 캐시                        0.0511 ms   x1.29

C. 펫 목록 + 알레르기 (user 1, 펫 3마리)
  n=300  (중앙값)
    C4 캐시+상관서브쿼리                       0.0344 ms   x1.00
    C1 조인+상관서브쿼리                       0.0357 ms   x1.04
    C3r 캐시+raw SELECT                  0.0646 ms   x1.88
    C2 조인+SELECT 2번                    0.0694 ms   x2.02
    C3 캐시+SELECT 2번                    0.0813 ms   x2.36

# test 2
    
A. 축종 이름 하나 (pet 80)
  n=300  (중앙값)
    JOIN 마스터                           0.0253 ms   x1.00
    raw SELECT + 캐시                    0.0267 ms   x1.06
    SELECT + 캐시                        0.0309 ms   x1.22

B. 알레르겐 이름 3개 (pet 80)
  n=300  (중앙값)
    JOIN 마스터                           0.0301 ms   x1.00
    raw SELECT + 캐시                    0.0321 ms   x1.07
    SELECT + 캐시                        0.0375 ms   x1.25

B. 알레르겐 이름 29개 (pet 66)
  n=300  (중앙값)
    raw SELECT + 캐시                    0.0396 ms   x1.00
    JOIN 마스터                           0.0441 ms   x1.11
    SELECT + 캐시                        0.0515 ms   x1.30

C. 펫 목록 + 알레르기 (user 1, 펫 3마리)
  n=300  (중앙값)
    C4 캐시+상관서브쿼리                       0.0343 ms   x1.00
    C1 조인+상관서브쿼리                       0.0353 ms   x1.03
    C3r 캐시+raw SELECT                  0.0660 ms   x1.92
    C2 조인+SELECT 2번                    0.0710 ms   x2.07
    C3 캐시+SELECT 2번                    0.0831 ms   x2.42

# test 3

A. 축종 이름 하나 (pet 80)
  n=300  (중앙값)
    raw SELECT + 캐시                    0.0252 ms   x1.00
    JOIN 마스터                           0.0253 ms   x1.00
    SELECT + 캐시                        0.0310 ms   x1.23

B. 알레르겐 이름 3개 (pet 80)
  n=300  (중앙값)
    JOIN 마스터                           0.0272 ms   x1.00
    raw SELECT + 캐시                    0.0276 ms   x1.01
    SELECT + 캐시                        0.0331 ms   x1.22

B. 알레르겐 이름 29개 (pet 66)
  n=300  (중앙값)
    raw SELECT + 캐시                    0.0398 ms   x1.00
    JOIN 마스터                           0.0406 ms   x1.02
    SELECT + 캐시                        0.0513 ms   x1.29

C. 펫 목록 + 알레르기 (user 1, 펫 3마리)
  n=300  (중앙값)
    C4 캐시+상관서브쿼리                       0.0345 ms   x1.00
    C1 조인+상관서브쿼리                       0.0357 ms   x1.03
    C3r 캐시+raw SELECT                  0.0663 ms   x1.92
    C2 조인+SELECT 2번                    0.0714 ms   x2.07
    C3 캐시+SELECT 2번                    0.0831 ms   x2.41

# test 4

A. 축종 이름 하나 (pet 80)
  n=300  (중앙값)
    raw SELECT + 캐시                    0.0253 ms   x1.00
    JOIN 마스터                           0.0256 ms   x1.01
    SELECT + 캐시                        0.0310 ms   x1.23

B. 알레르겐 이름 3개 (pet 80)
  n=300  (중앙값)
    JOIN 마스터                           0.0276 ms   x1.00
    raw SELECT + 캐시                    0.0277 ms   x1.00
    SELECT + 캐시                        0.0335 ms   x1.21

B. 알레르겐 이름 29개 (pet 66)
  n=300  (중앙값)
    JOIN 마스터                           0.0403 ms   x1.00
    raw SELECT + 캐시                    0.0431 ms   x1.07
    SELECT + 캐시                        0.0503 ms   x1.25

C. 펫 목록 + 알레르기 (user 1, 펫 3마리)
  n=300  (중앙값)
    C4 캐시+상관서브쿼리                       0.0363 ms   x1.00
    C1 조인+상관서브쿼리                       0.0473 ms   x1.30
    C3r 캐시+raw SELECT 2번               0.0677 ms   x1.87
    C2 조인+SELECT 2번                    0.0727 ms   x2.00
    C3 캐시+SELECT 2번                    0.0877 ms   x2.42
"""