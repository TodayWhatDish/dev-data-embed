# 반려동물 ORM 모델. 스키마 정의는 pipeline/create_schema/pet_schema.py

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)

from app.core.db import Base
from app.models import DATE_RE, DATETIME_RE

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
        CheckConstraint("length(trim(name)) > 0", name="ck_pet_name"),
        CheckConstraint("gender IN ('M', 'F')", name="ck_pet_gender"),
        # 하한은 고정값, 상한은 등록일이다 - CHECK 에 now() 를 쓰면 과거 행이 시간이 지나며 조건을 바꾼다.
        # 'YYYY-MM-DD' <= 'YYYY-MM-DD HH:MM:SS' 는 문자열 비교로 '등록일 당일까지' 가 된다.
        # '오늘 이후 금지' 는 API 가 한다
        CheckConstraint(
            f"birth_date ~ {DATE_RE} AND birth_date >= '1990-01-01' AND birth_date <= created_at",
            name="ck_pet_birth_date",
        ),
        CheckConstraint("weight_kg > 0 AND weight_kg <= 150", name="ck_pet_weight_kg"),
        CheckConstraint("size BETWEEN 1 AND 5", name="ck_pet_size"),
        CheckConstraint("body_type BETWEEN 1 AND 5", name="ck_pet_body_type"),
        CheckConstraint("activity_level BETWEEN 1 AND 3", name="ck_pet_activity_level"),
        CheckConstraint("neutered IN (0, 1)", name="ck_pet_neutered"),
        CheckConstraint(
            f"inactive_at ~ {DATETIME_RE} AND inactive_at >= created_at", name="ck_pet_inactive_at"
        ),
        CheckConstraint(f"created_at ~ {DATETIME_RE}", name="ck_pet_created_at"),
        CheckConstraint(f"updated_at ~ {DATETIME_RE} AND updated_at >= created_at", name="ck_pet_updated_at"),
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
    __table_args__ = (CheckConstraint(f"created_at ~ {DATETIME_RE}", name="ck_pet_survey_created_at"),)

    pet_id = Column(Integer, ForeignKey("pet.pet_id"), primary_key=True)
    diet_note = Column(Text)
    skin_note = Column(Text)
    created_at = Column(Text, nullable=False, server_default=NOW)
