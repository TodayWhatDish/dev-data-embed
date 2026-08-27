# Last Updated: 2026-08-17
"""
공유 코드표 — 반려동물 도메인과 제품 도메인이 함께 참조한다.

양쪽이 같은 ID 를 써야만 성립하는 값이라 어느 한쪽 모듈에 넣지 않았다.
  animal_category : breed / pet / product_animal_category 가 참조
  allergen         : pet_allergy / ingredient 가 참조

이 모듈은 다른 모듈에 의존하지 않는다. 그래서 execute_schema.MODULES 의 맨 앞이다.

설계 규칙 전문은 execute_schema.py, 컬럼 설명은 docu/schema/common_schema.md.
"""

TABLES = [

# animal_category — 축종 코드표. 컬럼 설명은 docu/schema/common_schema.md#animal_category
'''
CREATE TABLE animal_category (
    animal_category_id INTEGER NOT NULL PRIMARY KEY,
    name_ko            TEXT    NOT NULL UNIQUE,
    name_eng           TEXT    NOT NULL UNIQUE
) STRICT
''',

# allergen — 알러지원 마스터. 컬럼 설명은 docu/schema/common_schema.md#allergen
'''
CREATE TABLE allergen (
    allergen_id INTEGER NOT NULL PRIMARY KEY,
    parent_id   INTEGER REFERENCES allergen(allergen_id) ON DELETE RESTRICT,
    name_ko     TEXT    NOT NULL UNIQUE,
    name_eng    TEXT    UNIQUE
) STRICT
''',

]


INDEXES = [
    # "이 카테고리에 속한 원료 전부" — 계층 조회가 이 방향으로 탄다.
    'CREATE INDEX idx_allergen_parent      ON allergen(parent_id)',
]


# 코드표 초기 데이터 — 스키마의 일부다. 비어 있으면 FK 때문에 breed/pet 에 아무것도 못 넣는다.
SEEDS = [
    ("INSERT INTO animal_category(animal_category_id, name_ko, name_eng) VALUES (?, ?, ?)",
     [(1, '개', 'dog'), (2, '고양이', 'cat')]),
]
