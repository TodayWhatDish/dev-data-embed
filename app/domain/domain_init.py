from app.repositories.common import get_allergens, get_animal_categories
from app.repositories.pet import get_breeds
from app.repositories.products import get_product_categories, get_feeding_purposes, get_ingredients, get_ingredient_allergen_ids
from app.domain.products import ProductMgr
from app.domain.pet import PetMgr
from app.domain.common import CommonMgr
import logging

"""
DB로 부터 최초 1회 초기화해야하는 정보들 처리
"""

def init_from_db():
    """
    # Summary
    * 마스터 테이블을 통째로 읽어 도메인 싱글턴에 얹는다. 기동 시 1회.

    # info
    * 조립은 계층이 아니라 진입점 책임이라 이 파일만 domain 에서 repositories 를 안다.
    """

    logger = logging.getLogger()
    product_mgr = ProductMgr.get_inst()

    # 마스터 테이블은 기동 시 통째로 캐시한다 (docs/docu.md §1)
    # 도메인별로 나눠 담는다 — common: 축종/알러지(양쪽이 쓴다), pet: 품종, product: 카테고리/급여목적/원료
    common_mgr = CommonMgr.get_inst()
    common_mgr.set_allergen_info(get_allergens())
    common_mgr.set_animal_category(get_animal_categories())

    pet_mgr = PetMgr.get_inst()
    pet_mgr.set_breeds(get_breeds())

    product_mgr.set_product_category(get_product_categories())
    product_mgr.set_feeding_purpose(get_feeding_purposes())
    product_mgr.set_ingredient(get_ingredients())
    product_mgr.set_ingredient_allergen(get_ingredient_allergen_ids())

    logger.info(f'Cached master: allergen={len(common_mgr.get_all_allergen_hierarchy())}, '
                f'animal_category={len(common_mgr.get_animal_category())}, '
                f'breed={sum(len(b) for b in pet_mgr.get_all_breeds().values())}, '
                f'product_category={len(product_mgr.get_all_product_category_hierarchy())}, '
                f'feeding_purpose={len(product_mgr.get_feeding_purpose())}, '
                f'ingredient={len(product_mgr.get_ingredient())}, '
                f'ingredient_allergen={len(product_mgr.get_ingredient_allergen())}')
