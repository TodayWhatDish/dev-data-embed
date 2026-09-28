# 반려동물 ORM 모델. 스키마 정의는 pipeline/create_schema/pet_schema.py

from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, Index, Integer, Text, UniqueConstraint, text

from app.core.db import Base

# sqlite 의 datetime('now') 대신 - 컬럼이 TEXT ISO-8601 이라 Postgres now() 를 같은 포맷 문자열로 캐스팅한다
NOW = text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")


class Breed(Base):
    __tablename__ = "breed"
    __table_args__ = (
        UniqueConstraint("animal_category_id", "name_ko", name="uq_breed_name_ko"),
        UniqueConstraint("animal_category_id", "name_eng", name="uq_breed_name_eng"),
    )

    breed_id = Column(Integer, primary_key=True)
    animal_category_id = Column(Integer, ForeignKey("animal_category.animal_category_id"), nullable=False)
    name_ko = Column(Text, nullable=False)
    name_eng = Column(Text)


class Pet(Base):
    __tablename__ = "pet"
    __table_args__ = (
        CheckConstraint("gender IN ('M', 'F')", name="ck_pet_gender"),
        CheckConstraint("weight_kg > 0", name="ck_pet_weight_kg"),
        CheckConstraint("size BETWEEN 1 AND 5", name="ck_pet_size"),
        CheckConstraint("body_type BETWEEN 1 AND 5", name="ck_pet_body_type"),
        CheckConstraint("activity_level BETWEEN 1 AND 3", name="ck_pet_activity_level"),
        CheckConstraint("neutered IN (0, 1)", name="ck_pet_neutered"),
        Index("idx_pet_user", "user_id"),
    )

    pet_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    animal_category_id = Column(Integer, ForeignKey("animal_category.animal_category_id"), nullable=False)
    name = Column(Text, nullable=False)
    gender = Column(Text)
    birth_date = Column(Text)
    weight_kg = Column(Float)
    size = Column(Integer)
    body_type = Column(Integer)
    activity_level = Column(Integer)
    neutered = Column(Integer)
    inactive_at = Column(Text)
    created_at = Column(Text, nullable=False, server_default=NOW)
    updated_at = Column(Text, nullable=False, server_default=NOW)


class PetBreed(Base):
    __tablename__ = "pet_breed"
    __table_args__ = (Index("idx_pet_breed_breed", "breed_id"),)

    pet_id = Column(Integer, ForeignKey("pet.pet_id"), primary_key=True)
    breed_id = Column(Integer, ForeignKey("breed.breed_id"), primary_key=True)


class PetAllergy(Base):
    __tablename__ = "pet_allergy"

    pet_id = Column(Integer, ForeignKey("pet.pet_id"), primary_key=True)
    allergen_id = Column(Integer, ForeignKey("allergen.allergen_id"), primary_key=True)


class PetSurvey(Base):
    __tablename__ = "pet_survey"

    pet_id = Column(Integer, ForeignKey("pet.pet_id"), primary_key=True)
    diet_note = Column(Text)
    skin_note = Column(Text)
    created_at = Column(Text, nullable=False, server_default=NOW)
