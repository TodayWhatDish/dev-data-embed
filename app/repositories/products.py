from app.core.db import fetch, fetch_one, fetch_tuples, con, execute, QueryError
from app.repositories.general_query import (select, select_all, select_range,
                                            insert_query, update_query)
import logging

# 단일 테이블 + = 조건인 쿼리는 general_query 로 간다. SQL 을 손으로 쓰지 않는 것보다,
# 컬럼 이름이 틀렸을 때 QueryError('unknown_column') 로 통일되는 게 크다 —
# features/products.py 의 CLIENT_FAULT 표가 reason 을 보고 HTTP 상태를 정하기 때문이다.
# 조인·집계는 general_query 가 못 만들어서 아래에도 SQL 이 그대로 남아 있다.

# def get_product_detail_info():
#     fetch_tuples("""
#     SELECT *
#     FROM product
#     JOIN 
#     """)
#     pass

# # 벡터 디비 매핑을 위한 product의 모든 정보가 필요하다.

# def product_category_hierachy():
#     fetch_tuples("""
#     """
#           )
#     pass

def get_product_categories():
    return select_all("product_category")

def get_feeding_purposes():
    return select_all("feeding_purpose")

def get_ingredients():
    return select_all("ingredient")


# 아래는 임베딩 문장 재료. 이름은 마스터 캐시에 있으니 관계 테이블에서 id 만 긁어온다.
# 1:N 이라 조인하지 않고 전량 스캔 -> domain 에서 product_id 로 묶는다 (합쳐서 1500행 남짓)
#
# 관계 테이블 셋만 fetch_tuples 로 남는다. general_query 는 list[dict] 에 SELECT * 라
# 부르는 쪽의 for a, b in ... 을 전부 고쳐야 하고, 1500행 전량 스캔이라 컬럼 수도 공짜가 아니다

def get_products():
    return select("product", {"is_active": 1})

def get_product_animal_category_ids():
    return fetch_tuples("SELECT product_id, animal_category_id FROM product_animal_category")

def get_product_feeding_purpose_ids():
    return fetch_tuples("SELECT product_id, feeding_purpose_id FROM product_feeding_purpose")

def get_product_ingredient_ids():
    return fetch_tuples("SELECT product_id, ingredient_id FROM product_ingredient")

def get_product_nutritions():
    return select_all("product_nutrition")

def find_by_id(product_id: int) -> dict | None:
    """상품 한 건 조회. 없으면 None (예외가 아니다 — 부른 쪽이 404 를 정한다)"""
    rows = select("product", {"product_id": product_id})
    return rows[0] if rows else None

def find_page(page: int, size: int) -> list[dict]:
    """상품 여러 건 조회

    정렬을 걸어 둔다. ORDER BY 가 없으면 sqlite 가 순서를 보장하지 않는데, OFFSET 은
    '앞에서 몇 개' 를 건너뛰는 거라 페이지를 넘기는 사이 같은 상품이 두 번 나오거나 빠진다.
    product_id 는 PK 라 값이 안 겹쳐서 이것만으로 순서가 하나로 확정된다.

    size 가 0 이하이거나 page 가 음수면 QueryError('bad_range') 다. 예전엔 LIMIT 0 이 빈 목록,
    음수 OFFSET 이 0 으로 조용히 해석돼서 잘못된 요청이 티가 안 났다.
    """
    offset = page * size
    try:
        products = select_range("product", {}, size, offset, [("product_id", "ASC")])
    except QueryError as e:
        # 거절 사유와 실제로 계산된 offset 을 아는 건 여기다. features 는 page/size 만 안다
        logging.getLogger().warning(
            f"Reject find_page: reason={e.reason}, page={page}, size={size}, offset={offset}, detail={e.detail}")
        raise            # 인자 없는 raise 여야 원래 트레이스백이 안 날아간다

    logging.getLogger().debug(f"Find page product, page: {page}, size: {size}, rows: {len(products)}")
    return products

def insert(values: dict) -> int:
    """상품 한 건을 등록하고 새로 생긴 product_id를 돌려준다.

    거절당하면 QueryError 가 올라온다. 사유를 아는 건 execute 인데 무엇을 넣으려 했는지
    아는 건 여기라, 로그는 여기서 찍고 예외는 그대로 위로 넘긴다.
    """
    try:
        product_id = insert_query('product', values)
    except QueryError as e:
        logging.getLogger().warning(
            f"Reject insert product: reason={e.reason}, cols={list(values.keys())}, detail={e.detail}")
        raise            # 인자 없는 raise 여야 원래 트레이스백이 안 날아간다

    logging.getLogger().debug(f"Insert product, product_id: {product_id}, cols: {list(values.keys())}")
    return product_id


def update_product(product_id: int, values: dict) -> int:
    """상품 한 건을 수정하고 고친 행 수를 돌려준다. 없는 id 면 예외가 아니라 0 이다.

    거절당하면 QueryError 가 올라온다. 사유를 아는 건 general_query 인데 어느 테이블 몇 번인지
    아는 건 여기라, 로그는 여기서 찍고 예외는 그대로 위로 넘긴다.
    """
    try:
        return update_query('product', values, {'product_id' : product_id})
    except QueryError as e:
        logging.getLogger().warning(
            f"Reject update product: reason={e.reason}, product_id={product_id}, detail={e.detail}")
        raise            # 인자 없는 raise 여야 원래 트레이스백이 안 날아간다
    
def update(product_id: int, values: dict) -> int:
    """상품 한 건을 수정하고 고친 행 수를 돌려준다. 없는 id 면 예외가 아니라 0 이다."""
    sets = ", ".join(f"{k} = ?" for k in values)
    cur = execute(f"UPDATE product SET {sets} WHERE product_id = ?",
                  (*values.values(), product_id), 'product')
    return cur.rowcount

def inactive_product(product_id: int) -> int:
    """상품 한 건을 비활성화(is_active=0)하고 고친 행 수를 돌려준다. 없는 id 면 예외가 아니라 0 이다.

    행을 지우지 않는다 — 구매 이력이 product_id 를 참조하고 있어서 DELETE 는 constraint_fk 로
    막히거나 이력을 끊는다. 조회 쪽은 get_products / v_safe_products 가 is_active = 1 로 거른다.
    """
    return update_product(product_id, {'is_active': 0})

def get_ingredient_allergen_ids():
    return select_all("ingredient_allergen", None, ["ingredient_id", "allergen_id"])
