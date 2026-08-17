# Last Updated: 2026-08-17
"""
제품 — 판매 제품과 그 속성, 그리고 알러지 판정 뷰.

의존: common_schema (animal_categories, allergens).
      뷰 v_product_safety 는 pets / pet_allergies 까지 읽으므로 pet_schema 에도 의존한다.
      뷰는 참조 대상이 실재해야 CREATE 가 성립하므로 이 모듈이 MODULES 의 맨 뒤다.

뷰 2개가 여기 있는 이유: pets × products 를 걸치지만 목적이 제품 필터링이다.

설계 규칙 전문은 execute_schema.py, 컬럼 설명은 docu/schema/product_schema.md.
"""

TABLES = [

# product_categories — 제품 분류 코드표. 컬럼 설명은 docu/schema/product_schema.md#product_categories
'''
CREATE TABLE product_categories (
    product_category_id INTEGER NOT NULL PRIMARY KEY,
    parent_id           INTEGER REFERENCES product_categories(product_category_id) ON DELETE RESTRICT,
    name_ko             TEXT    NOT NULL UNIQUE,
    name_eng            TEXT    UNIQUE
) STRICT
''',

# feeding_purposes — 급여목적 코드표. 컬럼 설명은 docu/schema/product_schema.md#feeding_purposes
'''
CREATE TABLE feeding_purposes (
    feeding_purpose_id INTEGER NOT NULL PRIMARY KEY,
    name_ko            TEXT    NOT NULL UNIQUE,
    name_eng           TEXT    UNIQUE
) STRICT
''',

# products — 판매 제품. 컬럼 설명은 docu/schema/product_schema.md#products
'''
CREATE TABLE products (
    product_id           INTEGER NOT NULL PRIMARY KEY,
    product_category_id  INTEGER NOT NULL
        REFERENCES product_categories(product_category_id) ON DELETE RESTRICT,
    brand                TEXT    NOT NULL,
    name                 TEXT    NOT NULL,
    food_form            TEXT    CHECK (food_form IN ('건식', '습식', '동결건조', '생식', '공용')),
    price_krw            INTEGER NOT NULL CHECK (price_krw >= 0),
    weight_g             INTEGER NOT NULL CHECK (weight_g > 0),
    price_per_100g       INTEGER GENERATED ALWAYS AS (price_krw * 100 / weight_g) STORED,
    kcal_per_100g        INTEGER CHECK (kcal_per_100g > 0),

    -- 대상 범위. '전체'라는 마법값을 두지 않고 범위의 양 끝으로 표현한다.
    target_size_min      INTEGER NOT NULL DEFAULT 1
                         CHECK (target_size_min BETWEEN 1 AND 5),
    target_size_max      INTEGER NOT NULL DEFAULT 5
                         CHECK (target_size_max BETWEEN 1 AND 5),
    target_age_min_month INTEGER NOT NULL DEFAULT 0    CHECK (target_age_min_month >= 0),
    target_age_max_month INTEGER NOT NULL DEFAULT 1200 CHECK (target_age_max_month >= 0),

    description          TEXT,
    ingredients_verified INTEGER NOT NULL DEFAULT 0 CHECK (ingredients_verified IN (0, 1)),
    is_active            INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now')),

    CHECK (target_size_min <= target_size_max),
    CHECK (target_age_min_month <= target_age_max_month)
) STRICT
''',

# product_animal_categories — 제품 ↔ 축종 (다대다). 컬럼 설명은 docu/schema/product_schema.md#product_animal_categories
'''
CREATE TABLE product_animal_categories (
    product_id         INTEGER NOT NULL
        REFERENCES products(product_id)                     ON DELETE CASCADE,
    animal_category_id INTEGER NOT NULL
        REFERENCES animal_categories(animal_category_id)    ON DELETE RESTRICT,
    PRIMARY KEY (product_id, animal_category_id)
) STRICT, WITHOUT ROWID
''',

# product_nutrition — 제품 영양성분 (1:1). 컬럼 설명은 docu/schema/product_schema.md#product_nutrition
'''
CREATE TABLE product_nutrition (
    product_id        INTEGER NOT NULL PRIMARY KEY
        REFERENCES products(product_id) ON DELETE CASCADE,
    crude_protein_pct REAL CHECK (crude_protein_pct BETWEEN 0 AND 100),
    crude_fat_pct     REAL CHECK (crude_fat_pct     BETWEEN 0 AND 100),
    crude_fiber_pct   REAL CHECK (crude_fiber_pct   BETWEEN 0 AND 100),
    moisture_pct      REAL CHECK (moisture_pct      BETWEEN 0 AND 100),
    calcium_pct       REAL CHECK (calcium_pct       BETWEEN 0 AND 100),
    phosphorus_pct    REAL CHECK (phosphorus_pct    BETWEEN 0 AND 100),
    sodium_pct        REAL CHECK (sodium_pct        BETWEEN 0 AND 100)
) STRICT
''',

# product_feeding_purposes — 제품 ↔ 급여목적 (다대다). 컬럼 설명은 docu/schema/product_schema.md#product_feeding_purposes
'''
CREATE TABLE product_feeding_purposes (
    product_id         INTEGER NOT NULL
        REFERENCES products(product_id)                   ON DELETE CASCADE,
    feeding_purpose_id INTEGER NOT NULL
        REFERENCES feeding_purposes(feeding_purpose_id)   ON DELETE RESTRICT,
    PRIMARY KEY (product_id, feeding_purpose_id)
) STRICT, WITHOUT ROWID
''',

# ingredients — 원료 마스터. 컬럼 설명은 docu/schema/product_schema.md#ingredients
'''
CREATE TABLE ingredients (
    ingredient_id     INTEGER NOT NULL PRIMARY KEY,
    name_ko           TEXT    NOT NULL UNIQUE,
    allergen_id       INTEGER REFERENCES allergens(allergen_id) ON DELETE RESTRICT,
    allergen_reviewed INTEGER NOT NULL DEFAULT 0 CHECK (allergen_reviewed IN (0, 1)),

    -- 매핑을 넣었다는 것 자체가 검토했다는 뜻이다. 미검토인데 매핑이 있는 상태를 막는다.
    CHECK (allergen_id IS NULL OR allergen_reviewed = 1)
) STRICT
''',

# product_ingredients — 제품 ↔ 원료 (다대다). 컬럼 설명은 docu/schema/product_schema.md#product_ingredients
'''
CREATE TABLE product_ingredients (
    product_id    INTEGER NOT NULL
        REFERENCES products(product_id)         ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL
        REFERENCES ingredients(ingredient_id)   ON DELETE RESTRICT,
    PRIMARY KEY (product_id, ingredient_id)
) STRICT, WITHOUT ROWID
''',

]


INDEXES = [
    # "이 대분류의 소분류 전부" — 분류 트리를 앱이 통째로 읽을 때 탄다.
    'CREATE INDEX idx_product_categories_parent ON product_categories(parent_id)',

    # 후보군 1차 필터. product_category_id 가 선두인 것이 핵심이다 —
    # "간식만 보여줘" 처럼 카테고리 단독으로 거르는 조회(추천 경로를 안 타는 제품 목록)가
    # 그대로 SEARCH 로 붙는다. is_active 를 선두에 두면 이 조회가 풀스캔이 된다.
    # (값이 0/1 뿐이라 ANALYZE 를 돌린 뒤에는 skip-scan 이 붙지만,
    #  이 스크립트는 ANALYZE 를 돌리지 않으므로 갓 만든 DB 에서는 통계가 없어 풀스캔이다.)
    # 두 컬럼 모두 등호로 오는 후보군 필터는 순서와 무관하게 동일하게 탄다.
    # 잃는 것은 is_active 단독 조회뿐인데, 그건 활성 제품 전부를 뽑는 것이라 인덱스가 무의미하다.
    # 선두 컬럼이 FK 라 product_categories 부모행 삭제 검사도 이 인덱스가 겸한다.
    'CREATE INDEX idx_products_filter      ON products(product_category_id, is_active)',
    'CREATE INDEX idx_products_ppg         ON products(price_per_100g)',

    # 역방향 조회: "이 축종에게 줄 수 있는 제품 전부" — 후보군 필터가 이 방향으로 탄다.
    # 정방향("이 제품의 대상 축종들")은 복합 PK 의 선두 컬럼이 그대로 처리한다.
    'CREATE INDEX idx_prod_ac_category     ON product_animal_categories(animal_category_id)',

    # -- 역방향 조회: "이 알러지원을 가진 제품 전부" (배제 필터가 이 방향으로 탄다) --
    # 정방향("이 제품의 원료들")은 복합 PK 의 선두 컬럼이 그대로 처리한다.
    'CREATE INDEX idx_ingredients_allergen ON ingredients(allergen_id)',
    'CREATE INDEX idx_prod_ing_ingredient  ON product_ingredients(ingredient_id)',
    'CREATE INDEX idx_prod_fp_purpose      ON product_feeding_purposes(feeding_purpose_id)',
]


SEEDS = [
    # 대분류만 시드로 고정한다. 소분류는 관리자가 채운다 —
    # 사료의 소분류('건식사료'/'퍼피사료')는 food_form 과 target_age_* 가 이미 담고 있어
    # 여기에 또 만들면 같은 사실이 두 군데에 앉는다. 소분류가 의미를 갖는 쪽은 간식이다.
    ("INSERT INTO product_categories(product_category_id, parent_id, name_ko, name_eng) VALUES (?, ?, ?, ?)",
     [(1, None, '사료',   'food'),
      (2, None, '간식',   'treat'),
      (3, 2,    '덴탈껌', 'dental chew'),
      (4, 2,    '트릿',   'training treat'),
      (5, 2,    '수제간식', 'handmade treat')]),

    ("INSERT INTO feeding_purposes(feeding_purpose_id, name_ko, name_eng) VALUES (?, ?, ?)",
     [(1, '관절',     'joint'),
      (2, '다이어트', 'diet'),
      (3, '피부',     'skin'),
      (4, '치아',     'dental'),
      (5, '신장',     'renal'),
      (6, '소화',     'digestion')]),
]


VIEWS = [

    # v_product_safety — 반려동물 × 제품 알러지 판정. 추천 파이프라인의 첫 단계.
    # 판정 로직이 있는 곳은 여기 한 군데다. 설명은 docu/schema/product_schema.md#v_product_safety
    '''
CREATE VIEW v_product_safety AS
SELECT
    pt.pet_id,
    pr.product_id,
    CASE
        -- ① 알러지원이 확인됨 -> 배제(감점이 아니다)
        WHEN EXISTS (
                SELECT 1
                  FROM product_ingredients pi
                  JOIN ingredients   i  ON i.ingredient_id = pi.ingredient_id
                  JOIN pet_allergies pa ON pa.allergen_id  = i.allergen_id
                 WHERE pi.product_id = pr.product_id
                   AND pa.pet_id     = pt.pet_id
             ) THEN '위험'
        -- ② 원료표를 사람이 확인한 적이 없음
        WHEN pr.ingredients_verified = 0 THEN '판정불가'
        -- ③ 원료표는 등록됐지만 그중 알러지 검토가 안 끝난 원료가 있음
        WHEN EXISTS (
                SELECT 1
                  FROM product_ingredients pi
                  JOIN ingredients i ON i.ingredient_id = pi.ingredient_id
                 WHERE pi.product_id = pr.product_id
                   AND i.allergen_reviewed = 0
             ) THEN '판정불가'
        ELSE '안전'
    END AS verdict
FROM pets pt
-- 대상 축종에 이 아이의 축종이 등록된 제품만. 미등록(0행)은 후보에 뜨지 않는다.
JOIN product_animal_categories pac ON pac.animal_category_id = pt.animal_category_id
JOIN products                  pr  ON pr.product_id          = pac.product_id
WHERE pr.is_active   = 1
  AND pt.inactive_at IS NULL
''',

    # v_safe_products — 추천 후보군. '판정불가'를 통과시키는 정책으로 바꾸려면 이 뷰만 고친다.
    '''
CREATE VIEW v_safe_products AS
SELECT pet_id, product_id
FROM v_product_safety
WHERE verdict = '안전'
''',
]
