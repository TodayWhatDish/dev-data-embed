"""pet 자체검증 - repo 가 id 를 주고 domain 이 이름을 붙이는 두 단계가 맞물리는지 본다.

    py -m tests.domain_and_repo.pet
"""
import logging
from collections import Counter

from app.app_logger.logger import init_logger
from app.api.lifespan import load_domain_cache
from app.domain import pet as pet_domain
from app.repositories import pet as pet_repo
from app.repositories.general_query import select_all

logger = logging.getLogger()


if __name__ == '__main__':
    init_logger('test_pet')
    load_domain_cache()

    # 픽스처는 general_query 로 읽고 세는 건 파이썬에서 한다. general_query 는 집계도
    # IS NULL 도 못 만들고(= ? 가 아니다), 여기서 그걸 쓰는 게 이 계층을 같이 훑는 길이다
    pets = [r for r in select_all('pet') if r['inactive_at'] is None]
    counted = Counter(r['user_id'] for r in pets)
    user_id, pet_n = counted.most_common(1)[0]

    # 1. repo 는 마스터 이름을 안 붙인다. 여기서 이름이 오면 조인이 다시 기어들어온 것이다
    raw = pet_repo.find_pets_by_user(user_id)
    logger.info(f'user {user_id} 펫 {len(raw)}마리 (원본): {raw[0]}')
    assert len(raw) == pet_n
    assert 'animal_category_id' in raw[0] and 'animal_category' not in raw[0], raw[0]

    # 2. domain 이 붙인 뒤에야 이름이 생긴다. 원본은 안 고쳐야 한다 (부르는 쪽이 또 쓸 수 있어서)
    named = pet_domain.attach_names(raw)
    logger.info(f'이름 붙인 뒤: {named[0]}')
    assert named[0]['animal_category'] in ('개', '고양이'), named[0]
    assert isinstance(named[0]['allergies'], list)
    assert 'animal_category' not in raw[0], '원본이 오염됐다'

    # 3. 알레르기가 여럿인 펫에서 콤마 문자열이 제대로 갈라지는지. 한 마리짜리 경로도 같이 본다
    allergy_rows = select_all('pet_allergy')
    heavy, cnt = Counter(r['pet_id'] for r in allergy_rows).most_common(1)[0]
    one = pet_domain.attach_names_one(pet_repo.find_pet(heavy))
    logger.info(f'pet {heavy} 알레르기 {len(one["allergies"])}종: {one["allergies"][:3]} ...')
    assert len(one['allergies']) == cnt, one['allergies']
    assert all(isinstance(a, str) for a in one['allergies'])

    # 4. 알레르기가 없으면 None 이 아니라 빈 목록이다 (부르는 쪽이 None 검사를 안 하도록)
    has_allergy = {r['pet_id'] for r in allergy_rows}
    empty = next(r['pet_id'] for r in pets if r['pet_id'] not in has_allergy)
    assert pet_domain.attach_names_one(pet_repo.find_pet(empty))['allergies'] == []

    # 5. 없는 id 는 예외가 아니라 None 이고, domain 도 그 None 을 그대로 통과시킨다
    assert pet_repo.find_pet(-1) is None
    assert pet_domain.attach_names_one(None) is None

    # 6. 예전 조인 구현과 결과가 같은가. 이 리팩터링이 깨는 게 있다면 여기서 잡힌다
    #    (조인판은 tests/bench/master_join.py 의 c_join_subquery 가 그대로 들고 있다)
    from tests.bench.master_join import c_join_subquery
    before = [{'pet_id': r['pet_id'], 'name': r['name'],
               'animal_category': r['animal_category'], 'size': r['size'],
               'allergies': sorted((r['allergies'] or '').split(',')) if r['allergies'] else []}
              for r in c_join_subquery(user_id)]
    after = [{'pet_id': r['pet_id'], 'name': r['name'],
              'animal_category': r['animal_category'], 'size': r['size'],
              'allergies': sorted(r['allergies'])}
             for r in pet_domain.attach_names(pet_repo.find_pets_by_user(user_id))]
    assert before == after, f'조인판과 결과가 다르다: {before} != {after}'

    logger.info('ok')
