# 구매/후기 ORM 모델. 스키마 정의는 pipeline/create_schema/purchase_schema.py

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, Text, text

from app.core.db import Base


class Purchase(Base):
    __tablename__ = "purchase"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_quantity"),
        CheckConstraint("unit_price_krw >= 0", name="ck_purchase_unit_price_krw"),
        CheckConstraint("age_month_at_purchase >= 0", name="ck_purchase_age_month_at_purchase"),
        CheckConstraint("size_at_purchase BETWEEN 1 AND 5", name="ck_purchase_size_at_purchase"),
        Index("idx_purchase_pet", "pet_id", "purchased_at"),
        Index("idx_purchase_product", "product_id", "purchased_at"),
    )

    purchase_id = Column(Integer, primary_key=True)
    pet_id = Column(Integer, ForeignKey("pet.pet_id"), nullable=False)
    product_id = Column(Integer, ForeignKey("product.product_id"), nullable=False)
    quantity = Column(Integer, nullable=False, server_default=text("1"))
    unit_price_krw = Column(Integer, nullable=False)
    age_month_at_purchase = Column(Integer)
    size_at_purchase = Column(Integer)
    purchased_at = Column(Text, nullable=False)


class Review(Base):
    __tablename__ = "review"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating"),
        CheckConstraint("length(trim(body)) > 0", name="ck_review_body"),
        CheckConstraint("is_holdout IN (0, 1)", name="ck_review_is_holdout"),
    )

    purchase_id = Column(Integer, ForeignKey("purchase.purchase_id"), primary_key=True)
    rating = Column(Integer, nullable=False)
    body = Column(Text, nullable=False)
    is_holdout = Column(Integer, nullable=False, server_default=text("0"))
    reviewed_at = Column(Text, nullable=False)
