from app.repositories.common import get_col_names, get_allgens, get_animal_categories, get_breeds
from app.domain.product import ProductMgr
from app.domain.common import CommonMgr
import logging

"""
DB로 부터 최초 1회 초기화해야하는 정보들 처리
"""

def init_from_db():
    """
    Load product table columns name
    """
    
    logger = logging.getLogger()
    # singleton ProductMgr set product table columns
    product_mgr = ProductMgr.get_inst()
    product_mgr.set_col(get_col_names('product'))
    
    logger.info('Get product table columns')
    logger.info(f'product col: {product_mgr.get_col()}')

    # 마스터 테이블은 기동 시 통째로 캐시한다 (docs/docu.md §1)
    common_mgr = CommonMgr.get_inst()
    common_mgr.set_allergen_info(get_allgens())
    common_mgr.set_animal_category(get_animal_categories())
    common_mgr.set_breeds(get_breeds())

    logger.info(f'Cached master: allergen={len(common_mgr.get_allergen_names())}, '
                f'animal_category={len(common_mgr.get_animal_category())}')
    
    