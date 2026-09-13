# 반려동물 ORM 모델. 스키마 정의는 pipeline/create_schema/pet_schema.py

from sqlalchemy import Column, Float, ForeignKey, Integer, Text, text

from app.core.db import Base

NOW = text("(datetime('now'))")


class Breed(Base):
    __tablename__ = "breed"

    breed_id = Column(Integer, primary_key=True)
    animal_category_id = Column(Integer, ForeignKey("animal_category.animal_category_id"), nullable=False)
    name_ko = Column(Text, nullable=False)
    name_eng = Column(Text)


class Pet(Base):
    __tablename__ = "pet"

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
