# Last Updated: 2026-08-24
"""
구매와 후기 — 어떤 아이가 무엇을 샀고, 그래서 어땠는지.

의존: pet_schema (pets), product_schema (products).
      그래서 execute_schema.MODULES 에서 그 둘보다 뒤에 온다.

후기는 구매에 매달린다(reviews.purchase_id 가 PK 이자 FK). 구매 없이 쓴 후기는 받지 않는다 —
"실제 후기에서만 근거를 찾는다"가 서비스의 근거이므로 그 전제를 DB 가 지킨다.

알러지 반응 컬럼과 created_at/updated_at 을 왜 안 두는지는 md 에 있다.

설계 규칙 전문은 execute_schema.py, 컬럼 설명은 docu/schema/purchase_schema.md.
"""

TABLES = [

# purchases — 구매 이력. 컬럼 설명은 docu/schema/purchase_schema.md#purchases
'''
CREATE TABLE purchases (
    purchase_id           INTEGER NOT NULL PRIMARY KEY,
    pet_id                INTEGER NOT NULL
        REFERENCES pets(pet_id)         ON DELETE RESTRICT,
    product_id            INTEGER NOT NULL
        REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity              INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),

    -- 구매 시점의 값들. pets/products 를 조인하면 '지금' 값이 나온다. 근거는 md.
    unit_price_krw        INTEGER NOT NULL CHECK (unit_price_krw >= 0),      -- 그때 개당 가격
    age_month_at_purchase INTEGER CHECK (age_month_at_purchase >= 0),        -- 그때 나이. petcalc.age_months()
    size_at_purchase      INTEGER CHECK (size_at_purchase BETWEEN 1 AND 5),  -- 그때 체구. 정정 시 백필

    purchased_at          TEXT    NOT NULL CHECK (datetime(purchased_at) IS NOT NULL)
) STRICT
''',

# purchases 에 created_at / updated_at 은 없다 - UPDATE 가 없어 purchased_at 과 같은 값이 된다.

# reviews — 후기. 구매 1건당 최대 1건. 컬럼 설명은 docu/schema/purchase_schema.md#reviews
'''
CREATE TABLE reviews (
    purchase_id INTEGER NOT NULL PRIMARY KEY
        REFERENCES purchases(purchase_id) ON DELETE CASCADE,
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    body        TEXT    NOT NULL CHECK (length(trim(body)) > 0),

    is_holdout  INTEGER NOT NULL DEFAULT 0 CHECK (is_holdout IN (0, 1)),  -- 1 = 평가셋. 임베딩 제외
    reviewed_at TEXT    NOT NULL CHECK (datetime(reviewed_at) IS NOT NULL)
) STRICT
''',

]


INDEXES = [
    # "이 아이의 최근 구매" — 재구매 판정과 프로필 문맥이 전부 이 방향이다.
    # purchased_at 을 뒤에 붙여 정렬까지 인덱스가 처리한다(규칙 4: 날짜 단독 인덱스는 안 만든다).
    'CREATE INDEX idx_purchases_pet     ON purchases(pet_id, purchased_at)',

    # 역방향: "이 제품을 산 사람들" — 제품별 후기 목록이 reviews 를 거쳐 이 인덱스를 탄다.
    'CREATE INDEX idx_purchases_product ON purchases(product_id, purchased_at)',
]
