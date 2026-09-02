from app.core.db import query, dicts,one,con
from app.repositories.general_query import update_query
import sqlite3

# def get_product_detail_info():
#     query("""
#     SELECT *
#     FROM product
#     JOIN 
#     """)
#     pass

# # 벡터 디비 매핑을 위한 product의 모든 정보가 필요하다.

# def product_category_hierachy():
#     query("""
#     """
#           )
#     pass

def get_product_categories():
    return dicts("SELECT * FROM product_category")

def get_feeding_purposes():
    return dicts("SELECT * FROM feeding_purpose")

def get_ingredients():
    return dicts("SELECT * FROM ingredient")


# 아래는 임베딩 문장 재료. 이름은 마스터 캐시에 있으니 관계 테이블에서 id 만 긁어온다.
# 1:N 이라 조인하지 않고 전량 스캔 -> domain 에서 product_id 로 묶는다 (합쳐서 1500행 남짓)

def get_products():
    return dicts("SELECT * FROM product WHERE is_active = 1")

def get_product_animal_category_ids():
    return query("SELECT product_id, animal_category_id FROM product_animal_category")

def get_product_feeding_purpose_ids():
    return query("SELECT product_id, feeding_purpose_id FROM product_feeding_purpose")

def get_product_ingredient_ids():
    return query("SELECT product_id, ingredient_id FROM product_ingredient")

def get_product_nutritions():
    return dicts("SELECT * FROM product_nutrition")

def find_by_id(product_id: int) -> dict | None:
    """상품 한 건 조회"""
    rows = dicts("SELECT * FROM product WHERE product_id = ?", (product_id,))
    return rows[0] if rows else None

def find_page(page: int, size: int) -> list[dict]:
    """상품 여러 건 조회"""
    offset = page * size
    return dicts("SELECT * FROM product LIMIT ? OFFSET ?", (size, offset))

def insert(values: dict) -> int:
    """상품 한 건을 등록하고 새로 생긴 product_id를 돌려준다."""
    cols = ", ".join(values.keys())
    placeholders = ", ".join("?" for _ in values)
    cur = con.execute(f"INSERT INTO product ({cols}) VALUES ({placeholders})",
                          tuple(values.values()))
    con.commit()
    return cur.lastrowid


def update_product(product_id: int, values: dict) -> int:
    """상품 한 건을 수정하고 고친 행 수를 돌려준다. 없는 id 면 예외가 아니라 0 이다."""
    updated_cnt = update_query('product', values, {'product_id' : product_id})
    return updated_cnt
    
def update(product_id: int, values: dict) -> int:
    """상품 한 건을 수정하고 고친 행 수를 돌려준다. 없는 id 면 예외가 아니라 0 이다."""
    sets = ", ".join(f"{k} = ?" for k in values)
    cur = con.execute(f"UPDATE product SET {sets} WHERE product_id = ?",
               (*values.values(), product_id))
    con.commit()
    return cur.rowcount

def delete(product_id: int) -> int:
    """상품 한 건을 삭제하고 지운 행 수를 돌려준다. 없는 id 면 예외가 아니라 0 이다."""
    cur = con.execute("DELETE FROM product WHERE product_id = ?", (product_id,))
    con.commit()
    return cur.rowcount
    
def get_ingredient_allergen_ids():
    return query("SELECT ingredient_id, allergen_id FROM ingredient_allergen")
