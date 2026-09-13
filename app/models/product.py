# 제품 ORM 모델. 스키마 정의는 pipeline/create_schema/product_schema.py

from sqlalchemy import Column, Float, ForeignKey, Integer, Text, text

from app.core.db import Base

NOW = text("(datetime('now'))")


class ProductCategory(Base):
    __tablename__ = "product_category"

    product_category_id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("product_category.product_category_id"))
    name_ko = Column(Text, nullable=False)
    name_eng = Column(Text)


class FeedingPurpose(Base):
    __tablename__ = "feeding_purpose"

    feeding_purpose_id = Column(Integer, primary_key=True)
    name_ko = Column(Text, nullable=False)
    name_eng = Column(Text)


class Product(Base):
    __tablename__ = "product"

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

    product_id = Column(Integer, ForeignKey("product.product_id"), primary_key=True)
    animal_category_id = Column(Integer, ForeignKey("animal_category.animal_category_id"), primary_key=True)


class ProductNutrition(Base):
    __tablename__ = "product_nutrition"

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

    product_id = Column(Integer, ForeignKey("product.product_id"), primary_key=True)
    feeding_purpose_id = Column(Integer, ForeignKey("feeding_purpose.feeding_purpose_id"), primary_key=True)


class Ingredient(Base):
    __tablename__ = "ingredient"

    ingredient_id = Column(Integer, primary_key=True)
    name_ko = Column(Text, nullable=False)


class IngredientAllergen(Base):
    __tablename__ = "ingredient_allergen"

    ingredient_id = Column(Integer, ForeignKey("ingredient.ingredient_id"), primary_key=True)
    allergen_id = Column(Integer, ForeignKey("allergen.allergen_id"), primary_key=True)


class ProductIngredient(Base):
    __tablename__ = "product_ingredient"

    product_id = Column(Integer, ForeignKey("product.product_id"), primary_key=True)
    ingredient_id = Column(Integer, ForeignKey("ingredient.ingredient_id"), primary_key=True)
