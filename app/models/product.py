# 제품 ORM 모델. 스키마 정의는 pipeline/create_schema/product_schema.py

from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, Index, Integer, Text, text

from app.core.db import Base

# sqlite 의 datetime('now') 대신 - 컬럼이 TEXT ISO-8601 이라 Postgres now() 를 같은 포맷 문자열로 캐스팅한다
NOW = text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")


class ProductCategory(Base):
    __tablename__ = "product_category"
    __table_args__ = (Index("idx_product_category_parent", "parent_id"),)

    product_category_id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("product_category.product_category_id"))
    name_ko = Column(Text, nullable=False, unique=True)
    name_eng = Column(Text, unique=True)


class FeedingPurpose(Base):
    __tablename__ = "feeding_purpose"

    feeding_purpose_id = Column(Integer, primary_key=True)
    name_ko = Column(Text, nullable=False, unique=True)
    name_eng = Column(Text, unique=True)


class Product(Base):
    __tablename__ = "product"
    __table_args__ = (
        CheckConstraint("food_form IN ('건식', '습식', '동결건조', '생식', '공용')", name="ck_product_food_form"),
        CheckConstraint("price_krw >= 0", name="ck_product_price_krw"),
        CheckConstraint("weight_g > 0", name="ck_product_weight_g"),
        CheckConstraint("kcal_per_100g > 0", name="ck_product_kcal_per_100g"),
        CheckConstraint("target_size_min BETWEEN 1 AND 5", name="ck_product_target_size_min"),
        CheckConstraint("target_size_max BETWEEN 1 AND 5", name="ck_product_target_size_max"),
        CheckConstraint("target_age_min_month >= 0", name="ck_product_target_age_min_month"),
        CheckConstraint("target_age_max_month >= 0", name="ck_product_target_age_max_month"),
        CheckConstraint("ingredients_verified IN (0, 1)", name="ck_product_ingredients_verified"),
        CheckConstraint("is_active IN (0, 1)", name="ck_product_is_active"),
        CheckConstraint("target_size_min <= target_size_max", name="ck_product_target_size_range"),
        CheckConstraint("target_age_min_month <= target_age_max_month", name="ck_product_target_age_range"),
        Index("idx_product_filter", "product_category_id", "is_active"),
    )

    product_id = Column(Integer, primary_key=True)
    product_category_id = Column(Integer, ForeignKey("product_category.product_category_id"), nullable=False)
    brand = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    food_form = Column(Text)
    price_krw = Column(Integer, nullable=False)
    weight_g = Column(Integer, nullable=False)
    kcal_per_100g = Column(Integer)
    target_size_min = Column(Integer, nullable=False, server_default=text("1"))
    target_size_max = Column(Integer, nullable=False, server_default=text("5"))
    target_age_min_month = Column(Integer, nullable=False, server_default=text("0"))
    target_age_max_month = Column(Integer, nullable=False, server_default=text("1200"))
    description = Column(Text)
    ingredients_verified = Column(Integer, nullable=False, server_default=text("0"))
    is_active = Column(Integer, nullable=False, server_default=text("1"))
    created_at = Column(Text, nullable=False, server_default=NOW)
    updated_at = Column(Text, nullable=False, server_default=NOW)


class ProductAnimalCategory(Base):
    __tablename__ = "product_animal_category"
    __table_args__ = (Index("idx_prod_ac_category", "animal_category_id"),)

    product_id = Column(Integer, ForeignKey("product.product_id"), primary_key=True)
    animal_category_id = Column(Integer, ForeignKey("animal_category.animal_category_id"), primary_key=True)


class ProductNutrition(Base):
    __tablename__ = "product_nutrition"
    __table_args__ = (
        CheckConstraint("crude_protein_pct BETWEEN 0 AND 100", name="ck_nutrition_crude_protein_pct"),
        CheckConstraint("crude_fat_pct BETWEEN 0 AND 100", name="ck_nutrition_crude_fat_pct"),
        CheckConstraint("crude_fiber_pct BETWEEN 0 AND 100", name="ck_nutrition_crude_fiber_pct"),
        CheckConstraint("crude_ash_pct BETWEEN 0 AND 100", name="ck_nutrition_crude_ash_pct"),
        CheckConstraint("moisture_pct BETWEEN 0 AND 100", name="ck_nutrition_moisture_pct"),
        CheckConstraint("calcium_pct BETWEEN 0 AND 100", name="ck_nutrition_calcium_pct"),
        CheckConstraint("phosphorus_pct BETWEEN 0 AND 100", name="ck_nutrition_phosphorus_pct"),
        CheckConstraint("sodium_pct BETWEEN 0 AND 100", name="ck_nutrition_sodium_pct"),
    )

    product_id = Column(Integer, ForeignKey("product.product_id"), primary_key=True)
    crude_protein_pct = Column(Float)
    crude_fat_pct = Column(Float)
    crude_fiber_pct = Column(Float)
    crude_ash_pct = Column(Float)
    moisture_pct = Column(Float)
    calcium_pct = Column(Float)
    phosphorus_pct = Column(Float)
    sodium_pct = Column(Float)


class ProductFeedingPurpose(Base):
    __tablename__ = "product_feeding_purpose"
    __table_args__ = (Index("idx_prod_fp_purpose", "feeding_purpose_id"),)

    product_id = Column(Integer, ForeignKey("product.product_id"), primary_key=True)
    feeding_purpose_id = Column(Integer, ForeignKey("feeding_purpose.feeding_purpose_id"), primary_key=True)


class Ingredient(Base):
    __tablename__ = "ingredient"

    ingredient_id = Column(Integer, primary_key=True)
    name_ko = Column(Text, nullable=False, unique=True)


class IngredientAllergen(Base):
    __tablename__ = "ingredient_allergen"
    __table_args__ = (Index("idx_ing_allergen_allergen", "allergen_id"),)

    ingredient_id = Column(Integer, ForeignKey("ingredient.ingredient_id"), primary_key=True)
    allergen_id = Column(Integer, ForeignKey("allergen.allergen_id"), primary_key=True)


class ProductIngredient(Base):
    __tablename__ = "product_ingredient"
    __table_args__ = (Index("idx_prod_ing_ingredient", "ingredient_id"),)

    product_id = Column(Integer, ForeignKey("product.product_id"), primary_key=True)
    ingredient_id = Column(Integer, ForeignKey("ingredient.ingredient_id"), primary_key=True)
