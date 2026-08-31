from app.repositories.common import get_col_names
from app.domain.product import ProductMgr
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
    