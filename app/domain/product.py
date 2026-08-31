PRODUCT_FIELDS = (
    "brand", "product_name", "category", "sub_category",
    "target_feeding_purpose", "target_food_form",
    "ingredients", "tags", "description",
)

# ('product_id', 'product_category_id', 'brand', 'name', 'food_form', 'price_krw', 'weight_g', 'kcal_per_100g', 'target_size_min', 
# 'target_size_max', 'target_age_min_month', 'target_age_max_month', 'description', 'ingredients_verified', 'is_active', 'created_at', 'updated_at')

class ProductMgr:
    _instance = None
    def __init__(self):
        pass

    def set_col(self, cols: list[str]):
        self._product_col = tuple(col[0] for col in cols) # cols는 열 하나 짜리 여러 행 -> 열 하나 임을 [0]으로 인덱싱

    def get_col(self):
        return self._product_col
    
    @classmethod
    def get_inst(cls): #싱글턴 패턴을 위한
        if cls._instance == None:
            cls._instance = ProductMgr()
        return cls._instance

