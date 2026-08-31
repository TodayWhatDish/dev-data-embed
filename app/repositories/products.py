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
