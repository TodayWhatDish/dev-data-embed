# 구매/후기 ORM 모델. 스키마 정의는 pipeline/create_schema/purchase_schema.py

from sqlalchemy import Column, ForeignKey, Integer, Text, text

from app.core.db import Base


class Purchase(Base):
    __tablename__ = "purchase"

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

    purchase_id = Column(Integer, ForeignKey("purchase.purchase_id"), primary_key=True)
    rating = Column(Integer, nullable=False)
    body = Column(Text, nullable=False)
    is_holdout = Column(Integer, nullable=False, server_default=text("0"))
    reviewed_at = Column(Text, nullable=False)
