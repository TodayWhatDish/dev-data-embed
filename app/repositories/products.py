from app.core.db import query, dicts, con


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


def create_product(data: dict) -> int:
    """관리자 화면 상품등록 폼에서 넘어온 값으로 product 한 행을 만든다."""
    query("""
        INSERT INTO product (product_category_id, brand, name, food_form,
                              price_krw, weight_g, kcal_per_100g, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["product_category_id"], data["brand"], data["name"], data.get("food_form"),
        data["price_krw"], data["weight_g"], data.get("kcal_per_100g"), data.get("description"),
    ))
    con.commit()
    return query("SELECT last_insert_rowid()")[0][0]

def get_product_animal_category_ids():
    return query("SELECT product_id, animal_category_id FROM product_animal_category")

def get_product_feeding_purpose_ids():
    return query("SELECT product_id, feeding_purpose_id FROM product_feeding_purpose")

def get_product_ingredient_ids():
    return query("SELECT product_id, ingredient_id FROM product_ingredient")

def get_product_nutritions():
    return dicts("SELECT * FROM product_nutrition")
