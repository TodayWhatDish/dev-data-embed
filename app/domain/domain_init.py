from app.repositories.common import get_col_names, get_allgens
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

    common_mgr = CommonMgr.get_inst()
    common_mgr.set_allergen_info(get_allgens())
    
    