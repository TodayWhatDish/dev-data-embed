# Last Updated: 2026-08-17
"""
반려동물 — 유저가 소유한 개체와, 그 개체를 설명하는 어휘.

의존: common_schema (animal_categories, allergens), user_schema (users).
      그래서 execute_schema.MODULES 에서 그 둘보다 뒤에 온다.

설계 규칙 전문은 execute_schema.py, 컬럼 설명은 docu/schema/pet_schema.md.
"""

TABLES = [

# breeds — 품종 마스터. 컬럼 설명은 docu/schema/pet_schema.md#breeds
'''
CREATE TABLE breeds (
    breed_id           INTEGER NOT NULL PRIMARY KEY,
    animal_category_id INTEGER NOT NULL
        REFERENCES animal_categories(animal_category_id) ON DELETE RESTRICT,
    name_ko            TEXT    NOT NULL,
    name_eng           TEXT
) STRICT
''',

# pets — 반려동물 프로필. 컬럼 설명은 docu/schema/pet_schema.md#pets
'''
CREATE TABLE pets (
    pet_id             INTEGER NOT NULL PRIMARY KEY,
    user_id            INTEGER NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
    animal_category_id INTEGER NOT NULL
        REFERENCES animal_categories(animal_category_id) ON DELETE RESTRICT,
    name               TEXT    NOT NULL,
    gender             TEXT    CHECK (gender IN ('M', 'F')),
    birth_date         TEXT    CHECK (birth_date IS NULL OR date(birth_date) IS NOT NULL),
    weight_kg          REAL    CHECK (weight_kg > 0),
    size               INTEGER CHECK (size BETWEEN 1 AND 5),
    body_type          INTEGER CHECK (body_type BETWEEN 1 AND 5),
    neutered           INTEGER CHECK (neutered IN (0, 1)),
    inactive_at        TEXT    CHECK (inactive_at IS NULL OR datetime(inactive_at) IS NOT NULL),
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
) STRICT
''',

# pet_breeds — 반려동물 ↔ 품종 (다대다). 컬럼 설명은 docu/schema/pet_schema.md#pet_breeds
'''
CREATE TABLE pet_breeds (
    pet_id   INTEGER NOT NULL
        REFERENCES pets(pet_id)     ON DELETE CASCADE,
    breed_id INTEGER NOT NULL
        REFERENCES breeds(breed_id) ON DELETE RESTRICT,
    PRIMARY KEY (pet_id, breed_id)
) STRICT, WITHOUT ROWID
''',

# pet_allergies — 반려동물 ↔ 알러지원 (다대다). 컬럼 설명은 docu/schema/pet_schema.md#pet_allergies
'''
CREATE TABLE pet_allergies (
    pet_id      INTEGER NOT NULL
        REFERENCES pets(pet_id)           ON DELETE CASCADE,
    allergen_id INTEGER NOT NULL
        REFERENCES allergens(allergen_id) ON DELETE RESTRICT,
    PRIMARY KEY (pet_id, allergen_id)
) STRICT, WITHOUT ROWID
''',

]


INDEXES = [
    'CREATE INDEX idx_pets_user            ON pets(user_id)',

    # 역방향 조회: "이 품종을 가진 반려동물 전부" — 품종별 후기 집계가 이 방향으로 탄다.
    # 정방향("이 반려동물의 품종들")은 복합 PK 의 선두 컬럼이 그대로 처리한다.
    'CREATE INDEX idx_pet_breeds_breed     ON pet_breeds(breed_id)',
]


# 표기만 다른 같은 품종의 중복 등록을 막는다. 한글명에만 걸면
# '코커스패니얼'과 '코카스파니엘'이 서로 다른 문자열이라 그대로 통과한다.
UNIQUE_INDEXES = [
    'CREATE UNIQUE INDEX uq_breeds_name_ko  ON breeds(animal_category_id, name_ko)',
    'CREATE UNIQUE INDEX uq_breeds_name_eng ON breeds(animal_category_id, name_eng)',
]
