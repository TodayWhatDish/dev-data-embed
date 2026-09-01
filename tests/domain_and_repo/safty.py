import logging

from app.app_logger.logger import init_logger
from app.domain.common import CommonMgr
from app.domain.product import ProductMgr
from app.domain.safty import judge, WARN, UNKNOWN, SAFE
from app.domain.domain_init import init_from_db
from app.core.db import query, dicts


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
    ingredient_id, allergen_id = query(
        'SELECT ingredient_id, allergen_id FROM ingredient_allergen LIMIT 1')[0]
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
    verified = dicts('SELECT product_id, ingredients_verified FROM product')
    ingredients = {}
    for product_id, ing_id in query('SELECT product_id, ingredient_id FROM product_ingredient'):
        ingredients.setdefault(product_id, []).append(ing_id)

    pet_allergies = {}
    for pet_id, aid in query('SELECT pet_id, allergen_id FROM pet_allergy'):
        pet_allergies.setdefault(pet_id, []).append(aid)

    # query() 는 튜플 목록이라 한 컬럼이어도 (1,) 로 온다. 안 풀면 pet_allergies 조회가 전부 헛돈다
    pet_ids = [pet_id for pet_id, in query("SELECT pet_id FROM pet")]
    for ver_info in verified:
        p_id = ver_info["product_id"]
        is_verified = ver_info["ingredients_verified"]
        for pet_id in pet_ids:
            verdict, reason = judge(ingredients.get(p_id, []), pet_allergies.get(pet_id, []), is_verified)
            if verdict != '안전' and verdict != '판정불가':
                logger.info(f'product: {p_id}, pet: {pet_id}, is_safe: {verdict}, reason: {reason}')
    logger.info('ok')
