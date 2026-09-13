# 공유 코드표 ORM 모델 — animal_category, allergen. 스키마 정의는 pipeline/create_schema/common_schema.py

from sqlalchemy import Column, ForeignKey, Integer, Text

from app.core.db import Base


class AnimalCategory(Base):
    __tablename__ = "animal_category"

    animal_category_id = Column(Integer, primary_key=True)
    name_ko = Column(Text, nullable=False)
    name_eng = Column(Text, nullable=False)


class Allergen(Base):
    __tablename__ = "allergen"

    allergen_id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("allergen.allergen_id"))
    name_ko = Column(Text, nullable=False)
    name_eng = Column(Text)
