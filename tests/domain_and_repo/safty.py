import logging

from app.app_logger.logger import init_logger
from app.domain.common import CommonMgr
from app.domain.products import ProductMgr
from app.domain.safty import judge, WARN, UNKNOWN, SAFE
from app.domain.domain_init import init_from_db
from app.repositories.general_query import select_all, select_range


logger = logging.getLogger()


if __name__ == '__main__':
    init_logger('test_safty')
    init_from_db()
    product_mgr = ProductMgr.get_inst()
    common_mgr = CommonMgr.get_inst()

    # 재료에 해당하는 알러지
    allergen_of = product_mgr.get_ingredient_allergen
    # 알러지 id -> 알러지의 이름
    name_of = lambda aid: common_mgr.get_allergen(aid)['name_ko']

    # 알러지원이 붙은 원료 하나를 실제 데이터에서 고른다
    # 테스트를 위해 query 수행
    sample = select_range('ingredient_allergen', {}, 1, cols=['ingredient_id', 'allergen_id'])[0]
    ingredient_id, allergen_id = sample['ingredient_id'], sample['allergen_id']
    logger.info(f'표본 원료 {ingredient_id} -> 알러지원 {allergen_id}({name_of(allergen_id)})')

    # 1. 겹치면 위험 + 근거 문장에 알러지원 이름이 있다
    verdict, reason = judge([ingredient_id], [allergen_id], 1)
    logger.info(f'{verdict} {reason}')
    assert verdict == WARN, verdict
    assert name_of(allergen_id) in reason, reason

    # 2. 안 겹치고 원료표를 확인했으면 안전
    verdict, reason = judge([ingredient_id], [], 1)
    assert (verdict, reason) == (SAFE, ''), (verdict, reason)

    # 3. 안 겹쳐도 원료표 미확인이면 판정불가 — 모르는 것을 안전으로 처리하지 않는다
    verdict, reason = judge([ingredient_id], [], 0)
    logger.info(f'{verdict} {reason}')
    assert verdict == UNKNOWN, verdict

    # 4. 알러지원이 겹치면 원료표 미확인이어도 위험이 우선한다
    verdict, _ = judge([ingredient_id], [allergen_id], 0)
    assert verdict == WARN, verdict

    # 5. 알러지원이 없는 원료 id 는 빈 목록 — 조회 자체가 터지지 않는다
    assert allergen_of(999999) == []

    # 6. 뷰 v_product_safety 와 판정이 같아야 한다 (규칙이 두 군데라 어긋나면 여기서 잡는다)
    verified = select_all('product', cols=['product_id', 'ingredients_verified'])
    ingredients = {}
    for row in select_all('product_ingredient', cols=['product_id', 'ingredient_id']):
        ingredients.setdefault(row['product_id'], []).append(row['ingredient_id'])

    pet_allergies = {}
    for row in select_all('pet_allergy', cols=['pet_id', 'allergen_id']):
        pet_allergies.setdefault(row['pet_id'], []).append(row['allergen_id'])

    # general_query 는 컬럼 이름이 붙은 dict 로 준다. 튜플을 벗기던 자리가 없어진다
    pet_ids = [row['pet_id'] for row in select_all('pet', cols=['pet_id'])]
    for ver_info in verified:
        p_id = ver_info["product_id"]
        is_verified = ver_info["ingredients_verified"]
        for pet_id in pet_ids:
            verdict, reason = judge(ingredients.get(p_id, []), pet_allergies.get(pet_id, []), is_verified)
            if verdict != '안전' and verdict != '판정불가':
                logger.info(f'product: {p_id}, pet: {pet_id}, is_safe: {verdict}, reason: {reason}')
    logger.info('ok')
