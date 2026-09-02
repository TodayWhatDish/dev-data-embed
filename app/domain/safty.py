"""
상품이 반려동물의 알러지원을 가졌는지 판정한다.

판정 규칙이 있는 곳은 세 군데다 — DB 뷰 v_product_safety(pipeline/create_schema/product_schema.py),
검색 선필터 retrieve.FILTERS['allergy'], 그리고 여기. 하나를 고치면 셋 다 고친다
(CLAUDE.md 도메인 규칙 1). 뷰는 pet x product 전량을 걸러 후보를 만들고,
여기서는 이미 뽑아 둔 후보에 "왜 걸렸는지" 근거를 붙인다 — 근거 없는 차단은 사람이 못 고친다.
"""

from app.domain.common import CommonMgr
from app.domain.products import ProductMgr

WARN = '위험'
UNKNOWN = '판정불가'
SAFE = '안전'


def _hit_allergens(ingredient_ids, pet_allergen_ids):
    """
    # Summary
    * 상품 원료 -> 알러지 변환
    * 펫이 가진 알러지와 제품이 가진 모든 알러지의 교집합을 반환

    # info
    * 반환: {allergen_id, ...} — 비어 있으면 겹치는 알러지원이 없다는 뜻
    * 재료 -> 알러지 정보는 싱글턴으로 서버가 메모리로 가지고 있음

    # params
    * ingredient_ids: 그 상품의 원료 id 목록 (product_ingredient)
    * pet_allergen_ids: 그 반려동물에게 등록된 알러지원 id 목록 (pet_allergy)z
    """

    allergen_of_ingredient = ProductMgr.get_inst().get_ingredient_allergen


    # 제품이 가진 재료 -> 알러지 정보 추출하여 set으로 저장
    product_allergens = {allergen_id
                         for ingredient_id in ingredient_ids
                         for allergen_id in allergen_of_ingredient(ingredient_id)}

    # 교집합을 확인
    return product_allergens & set(pet_allergen_ids)


def judge(product_ingredient_ids, pet_allergen_ids, ingredients_verified):
    """
    # Summary
    * 상품 한 건에 대한 판정과 근거 문장을 반환. DB 에 닿지 않는다 — 마스터 캐시만 읽는다
    * 모르는 것을 안전으로 처리하지 않는다 — 원료표 미확인은 안전이 아니라 판정불가다
      (CLAUDE.md 도메인 규칙 2)

    # info
    * 반환: (판정, 근거 문장)
    * 판정: WARN(위험) / UNKNOWN(판정불가) / SAFE(안전) 3분법
    * 근거 문장: 안전이면 빈 문자열
    
    # params
    * product_ingredient_ids: 그 상품의 원료 id 목록 (product_ingredient)
    * pet_allergen_ids: 그 반려동물에게 등록된 알러지원 id 목록 (pet_allergy)
    * ingredients_verified: product.ingredients_verified. 0 이면 원료표를 사람이 확인한 적이 없다
    """
    if not product_ingredient_ids:
        return UNKNOWN, '원료표가 존재하지 않을 수 없습니다.'
    
    hits = _hit_allergens(product_ingredient_ids, pet_allergen_ids)

    if hits:
        common = CommonMgr.get_inst()
        names = ', '.join(sorted(common.get_allergen(aid)['name_ko'] for aid in hits))
        return WARN, f'{names} 알러지원이 들어 있습니다'

    if not ingredients_verified or ingredients_verified == 0:
        return UNKNOWN, '원료표를 사람이 확인한 적이 없습니다'

    return SAFE, ''
