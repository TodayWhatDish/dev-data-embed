from app.core.db import query, dicts


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

def get_ingredient_allergen_ids():
    return query("SELECT ingredient_id, allergen_id FROM ingredient_allergen")
