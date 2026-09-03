# Last Updated: 2026-08-17
"""
반려동물 — 유저가 소유한 개체와, 그 개체를 설명하는 어휘.

의존: common_schema (animal_category, allergen), user_schema (user).
      그래서 execute_schema.MODULES 에서 그 둘보다 뒤에 온다.

설계 규칙 전문은 execute_schema.py, 컬럼 설명은 docu/schema/pet_schema.md.
"""

TABLES = [

# breed — 품종 마스터. 컬럼 설명은 docu/schema/pet_schema.md#breed
'''
CREATE TABLE breed (
    breed_id           INTEGER NOT NULL PRIMARY KEY,
    animal_category_id INTEGER NOT NULL
        REFERENCES animal_category(animal_category_id) ON DELETE RESTRICT,
    name_ko            TEXT    NOT NULL,
    name_eng           TEXT
) STRICT
''',

# pet — 반려동물 프로필. 컬럼 설명은 docu/schema/pet_schema.md#pet
'''
CREATE TABLE pet (
    pet_id             INTEGER NOT NULL PRIMARY KEY,
    -- RESTRICT 다. CASCADE 면 계정 삭제 한 줄이 pet -> purchase -> review 를 타고
    -- 후기까지 지운다. 탈퇴는 user.withdrawn_at, 파기는 익명화 UPDATE 이므로
    -- 계정 행을 지우는 경로 자체를 DB 가 막는다(docu.md §1).
    user_id            INTEGER NOT NULL
        REFERENCES user(user_id) ON DELETE RESTRICT,
    animal_category_id INTEGER NOT NULL
        REFERENCES animal_category(animal_category_id) ON DELETE RESTRICT,
    name               TEXT    NOT NULL,
    gender             TEXT    CHECK (gender IN ('M', 'F')),
    birth_date         TEXT    CHECK (birth_date IS NULL OR date(birth_date) IS NOT NULL),
    weight_kg          REAL    CHECK (weight_kg > 0),
    size               INTEGER CHECK (size BETWEEN 1 AND 5),
    body_type          INTEGER CHECK (body_type BETWEEN 1 AND 5),
    -- body_type 과 같은 성격(보호자 판단, 오래 안 변함)이라 pet 에 둔다.
    -- 1 적음 / 2 보통 / 3 많음
    activity_level     INTEGER CHECK (activity_level BETWEEN 1 AND 3),
    neutered           INTEGER CHECK (neutered IN (0, 1)),
    inactive_at        TEXT    CHECK (inactive_at IS NULL OR datetime(inactive_at) IS NOT NULL),
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
) STRICT
''',

# pet_breed — 반려동물 ↔ 품종 (다대다). 컬럼 설명은 docu/schema/pet_schema.md#pet_breed
'''
CREATE TABLE pet_breed (
    pet_id   INTEGER NOT NULL
        REFERENCES pet(pet_id)     ON DELETE CASCADE,
    breed_id INTEGER NOT NULL
        REFERENCES breed(breed_id) ON DELETE RESTRICT,
    PRIMARY KEY (pet_id, breed_id)
) STRICT, WITHOUT ROWID
''',

# pet_allergy — 반려동물 ↔ 알러지원 (다대다). 컬럼 설명은 docu/schema/pet_schema.md#pet_allergy
'''
CREATE TABLE pet_allergy (
    pet_id      INTEGER NOT NULL
        REFERENCES pet(pet_id)           ON DELETE CASCADE,
    allergen_id INTEGER NOT NULL
        REFERENCES allergen(allergen_id) ON DELETE RESTRICT,
    PRIMARY KEY (pet_id, allergen_id)
) STRICT, WITHOUT ROWID
''',

# pet_survey — 가입 설문 스냅샷(식성/피부). pet 컬럼이 아니다 - 필터로 안 쓰고
# 추천 검색 질의문 재료 + 관리자 요약 표시로만 쓴다. 컬럼 설명은 docu/schema/pet_schema.md#pet_survey
'''
CREATE TABLE pet_survey (
    pet_id     INTEGER NOT NULL PRIMARY KEY
        REFERENCES pet(pet_id) ON DELETE CASCADE,
    diet_note  TEXT,
    skin_note  TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
) STRICT
''',

]


INDEXES = [
    'CREATE INDEX idx_pet_user             ON pet(user_id)',

    # 역방향 조회: "이 품종을 가진 반려동물 전부" — 품종별 후기 집계가 이 방향으로 탄다.
    # 정방향("이 반려동물의 품종들")은 복합 PK 의 선두 컬럼이 그대로 처리한다.
    'CREATE INDEX idx_pet_breed_breed      ON pet_breed(breed_id)',
]


# 표기만 다른 같은 품종의 중복 등록을 막는다. 한글명에만 걸면
# '코커스패니얼'과 '코카스파니엘'이 서로 다른 문자열이라 그대로 통과한다.
UNIQUE_INDEXES = [
    'CREATE UNIQUE INDEX uq_breed_name_ko  ON breed(animal_category_id, name_ko)',
    'CREATE UNIQUE INDEX uq_breed_name_eng ON breed(animal_category_id, name_eng)',
]
