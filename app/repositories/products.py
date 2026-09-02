from app.core.db import fetch, fetch_one, fetch_tuples, con, execute, QueryError
from app.repositories.general_query import update_query
import logging
import sqlite3

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
    return fetch("SELECT * FROM product_category")

def get_feeding_purposes():
    return fetch("SELECT * FROM feeding_purpose")

def get_ingredients():
    return fetch("SELECT * FROM ingredient")


# 아래는 임베딩 문장 재료. 이름은 마스터 캐시에 있으니 관계 테이블에서 id 만 긁어온다.
# 1:N 이라 조인하지 않고 전량 스캔 -> domain 에서 product_id 로 묶는다 (합쳐서 1500행 남짓)

def get_products():
    return fetch("SELECT * FROM product WHERE is_active = 1")

def get_product_animal_category_ids():
    return fetch_tuples("SELECT product_id, animal_category_id FROM product_animal_category")

def get_product_feeding_purpose_ids():
    return fetch_tuples("SELECT product_id, feeding_purpose_id FROM product_feeding_purpose")

def get_product_ingredient_ids():
    return fetch_tuples("SELECT product_id, ingredient_id FROM product_ingredient")

def get_product_nutritions():
    return fetch("SELECT * FROM product_nutrition")

def find_by_id(product_id: int) -> dict | None:
    """상품 한 건 조회"""
    return fetch_one("SELECT * FROM product WHERE product_id = ?", (product_id,))

def find_page(page: int, size: int) -> list[dict]:
    """상품 여러 건 조회"""
    offset = page * size
    return fetch("SELECT * FROM product LIMIT ? OFFSET ?", (size, offset))

def insert(values: dict) -> int:
    """상품 한 건을 등록하고 새로 생긴 product_id를 돌려준다."""
    cols = ", ".join(values.keys())
    placeholders = ", ".join("?" for _ in values)
    cur = execute(f"INSERT INTO product ({cols}) VALUES ({placeholders})",
                  tuple(values.values()), 'product')
    return cur.lastrowid


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

def delete(product_id: int) -> int:
    """상품 한 건을 삭제하고 지운 행 수를 돌려준다. 없는 id 면 예외가 아니라 0 이다."""
    cur = execute("DELETE FROM product WHERE product_id = ?", (product_id,), 'product')
    return cur.rowcount
    
def get_ingredient_allergen_ids():
    return fetch_tuples("SELECT ingredient_id, allergen_id FROM ingredient_allergen")
