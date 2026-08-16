# Last Updated: 2026-08-16
"""
'오늘 뭐먹냥' user.db 스키마 (1단계 — 추천 경로).

설계 규칙
  1) 모든 PK 는 INTEGER PRIMARY KEY (SQLite rowid 별칭).
     - 테이블 B-tree 가 정수로 직접 키잉되어 별도 인덱스가 생기지 않는다.
     - 조인이 문자열 비교가 아니라 64비트 정수 비교가 된다.
     - SQLite 에 unsigned 타입은 없다. uint32/uint64 는 STRICT 에서 에러이고,
       비STRICT 에서도 그냥 INTEGER 로 해석될 뿐 아무 제약이 없다.
       INTEGER 는 값 크기에 따라 1~8바이트로 가변 저장되므로 폭 지정도 무의미하다.

  2) 다대다 연결 테이블은 번호 컬럼을 따로 두지 않고, 두 FK 를 묶어서 PK 로 쓴다.

     "한 마리가 여러 품종을 갖고, 한 품종은 여러 마리가 갖는다"를 이렇게 표현한다.

         pet_breeds
         ┌────────┬──────────┐
         │ pet_id │ breed_id │
         ├────────┼──────────┤
         │      3 │        1 │  초코 - 포메라니안  ┐ 초코는 믹스라 2행
         │      3 │        7 │  초코 - 치와와      ┘
         │      5 │        1 │  보리 - 포메라니안
         └────────┴──────────┘
          └──── 이 둘을 합쳐서 PRIMARY KEY ────┘

     pet_breed_id 같은 번호를 붙이지 않는 이유:
       - (pet_id, breed_id) 조합이 이미 행 하나를 정확히 가리킨다.
       - 그 번호를 FK 로 참조할 다른 테이블이 없다. 붙여도 아무도 안 쓴다.
       - PK 로 잡아두면 "초코에게 포메라니안을 두 번 등록"이 그냥 막힌다.
         번호를 PK 로 두면 이걸 막는 UNIQUE 인덱스를 따로 챙겨야 하고,
         빠뜨리면 중복이 조용히 들어간다.

     조회 방향에 따라 인덱스가 다르다. PK 는 앞 컬럼 기준으로만 정렬돼 있다.
       WHERE pet_id = 3    -> PK 의 앞 컬럼이라 그대로 탄다. 추가 인덱스 불필요.
       WHERE breed_id = 1  -> PK 를 못 탄다. 이 방향을 쓴다면 인덱스를 따로 만든다.

     끝에 WITHOUT ROWID 를 붙인다. 그러면 PK 가 곧 테이블의 저장 순서가 되어
     인덱스라는 별도 구조가 아예 생기지 않는다.

  3) 상태(status)를 저장하지 않고 사실(타임스탬프)만 저장해 파생시킨다.
     휴면 = last_login_at 에서 계산, 탈퇴 = withdrawn_at IS NOT NULL.

  4) 날짜/시각은 TEXT ISO-8601. SQLite 에 DATE 타입이 없으므로 CHECK 로 형식만 강제한다.
     ISO-8601 을 쓰는 이유는 표기 통일뿐 아니라 정렬 때문이다 —
     'YYYY-MM-DD' 는 사전순 == 시간순이라 문자열 비교만으로 범위 조회와 ORDER BY 가 성립한다.
     날짜 컬럼에 단독 인덱스는 걸지 않는다. 실제 조회가 "특정 반려견의 최근 구매"처럼
     항상 부모 ID 로 먼저 좁혀지므로, 필요해지면 (pet_id, purchased_at) 복합으로 만든다.
     purchased_at 단독 인덱스는 전체 기간 통계 같은 관리자 쿼리에나 쓰이는데,
     그건 빈도가 낮아 풀스캔으로 충분하다.

  5) 금액은 INTEGER(원 단위). REAL 은 반올림 오차가 생긴다.

  6) 불리언은 INTEGER + CHECK IN (0,1). SQLite 에 BOOL 이 없다.
     현재 대상: pets.neutered, products.is_active, reviews.is_holdout.

  7) STRICT 테이블 — 선언한 타입과 다른 값은 INSERT 가 거부된다. 끄지 않는다.
     CSV 로더는 문자열을 int()/float() 로 캐스팅해서 넣어야 하는데, 이건 부담이 아니라
     의도한 결과다. 캐스팅이 실패하는 값은 애초에 그 컬럼에 들어가면 안 되는 값이라
     로딩 시점에 드러나는 편이 낫다. STRICT 가 없으면 '삼만원' 같은 값이 INTEGER
     컬럼에 TEXT 로 조용히 앉아 있다가 나중에 비교·정렬에서 틀린 답을 낸다.

실행: py src/create_schema/create_schema.py   (repo root 에서, SQLite 3.37+ 필요)
"""

import sqlite3

DB_PATH = 'user.db'

# 전 테이블 STRICT. 타입 강제는 이 스키마의 전제이므로 끄는 스위치를 두지 않는다.
STRICT = ' STRICT'


# ===========================================================================
# A. 보호자 / 반려견
# ===========================================================================

TABLES = [

# users — 보호자 계정. 컬럼 설명은 docu/SCHEMA.md#users
f'''
CREATE TABLE users (
    user_id       INTEGER NOT NULL PRIMARY KEY,
    auth_provider TEXT    NOT NULL DEFAULT 'local'
                          CHECK (auth_provider IN ('google', 'firebase', 'kakao', 'apple', 'local')),
    auth_uid      TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    phone         TEXT,
    region        TEXT,
    last_login_at TEXT    CHECK (last_login_at IS NULL OR datetime(last_login_at) IS NOT NULL),
    withdrawn_at  TEXT    CHECK (withdrawn_at IS NULL OR datetime(withdrawn_at) IS NOT NULL),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
){STRICT}
''',

# animal_categories — 축종 코드표. 컬럼 설명은 docu/SCHEMA.md#animal_categories
f'''
CREATE TABLE animal_categories (
    animal_category_id INTEGER NOT NULL PRIMARY KEY,
    name_ko            TEXT    NOT NULL UNIQUE,
    name_eng           TEXT    NOT NULL UNIQUE
){STRICT}
''',

# breeds — 품종 마스터. 컬럼 설명은 docu/SCHEMA.md#breeds
f'''
CREATE TABLE breeds (
    breed_id           INTEGER NOT NULL PRIMARY KEY,
    animal_category_id INTEGER NOT NULL
        REFERENCES animal_categories(animal_category_id) ON DELETE RESTRICT,
    name_ko            TEXT    NOT NULL,
    name_eng           TEXT
){STRICT}
''',

# allergens — 알러지원 마스터. 컬럼 설명은 docu/SCHEMA.md#allergens
f'''
CREATE TABLE allergens (
    allergen_id INTEGER NOT NULL PRIMARY KEY,
    parent_id   INTEGER REFERENCES allergens(allergen_id) ON DELETE RESTRICT,
    name_ko     TEXT    NOT NULL UNIQUE,
    name_eng    TEXT    UNIQUE
){STRICT}
''',

# pets — 반려동물 프로필. 컬럼 설명은 docu/SCHEMA.md#pets
f'''
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
){STRICT}
''',

# pet_breeds — 반려동물 ↔ 품종 (다대다). 컬럼 설명은 docu/SCHEMA.md#pet_breeds
f'''
CREATE TABLE pet_breeds (
    pet_id   INTEGER NOT NULL
        REFERENCES pets(pet_id)     ON DELETE CASCADE,
    breed_id INTEGER NOT NULL
        REFERENCES breeds(breed_id) ON DELETE RESTRICT,
    PRIMARY KEY (pet_id, breed_id)
){STRICT}, WITHOUT ROWID
''',

# pet_allergies — 반려동물 ↔ 알러지원 (다대다). 컬럼 설명은 docu/SCHEMA.md#pet_allergies
f'''
CREATE TABLE pet_allergies (
    pet_id      INTEGER NOT NULL
        REFERENCES pets(pet_id)           ON DELETE CASCADE,
    allergen_id INTEGER NOT NULL
        REFERENCES allergens(allergen_id) ON DELETE RESTRICT,
    PRIMARY KEY (pet_id, allergen_id)
){STRICT}, WITHOUT ROWID
''',

]


# ===========================================================================
# 인덱스
# ===========================================================================

INDEXES = [
    'CREATE INDEX idx_pets_user            ON pets(user_id)',

    # 역방향 조회: "이 품종을 가진 반려동물 전부" — 품종별 후기 집계가 이 방향으로 탄다.
    # 정방향("이 반려동물의 품종들")은 복합 PK 의 선두 컬럼이 그대로 처리한다.
    'CREATE INDEX idx_pet_breeds_breed     ON pet_breeds(breed_id)',

    # "이 카테고리에 속한 원료 전부" — 계층 조회가 이 방향으로 탄다.
    'CREATE INDEX idx_allergens_parent     ON allergens(parent_id)',
]


# ===========================================================================
# UNIQUE 인덱스 — 중복 등록 방지. PK 와 별개로 '자연키'를 여기서 강제한다.
# 목적별 설명은 docu/SCHEMA.md
# ===========================================================================

UNIQUE_INDEXES = [
    'CREATE UNIQUE INDEX uq_users_auth     ON users(auth_provider, auth_uid)',
    'CREATE UNIQUE INDEX uq_breeds_name_ko  ON breeds(animal_category_id, name_ko)',
    'CREATE UNIQUE INDEX uq_breeds_name_eng ON breeds(animal_category_id, name_eng)',
]


# ===========================================================================
# 코드표 초기 데이터 — 스키마의 일부다. 비어 있으면 FK 때문에 아무것도 못 넣는다.
# ===========================================================================

SEEDS = [
    ("INSERT INTO animal_categories(animal_category_id, name_ko, name_eng) VALUES (?, ?, ?)",
     [(1, '개', 'dog'), (2, '고양이', 'cat')]),
]


# ===========================================================================
# 뷰
# ===========================================================================

VIEWS = [
]


# DROP 순서는 FK 역순 (자식 -> 부모)
DROP_VIEWS = []
DROP_TABLES = [
    'pet_allergies', 'pet_breeds',
    'pets', 'allergens', 'breeds', 'animal_categories', 'users',
]


def create_schema(db_path=DB_PATH):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute('PRAGMA foreign_keys = OFF')     # DROP 중에는 끈다

    for name in DROP_VIEWS:
        cur.execute(f'DROP VIEW IF EXISTS {name}')
    for name in DROP_TABLES:
        cur.execute(f'DROP TABLE IF EXISTS {name}')

    for ddl in TABLES:
        cur.execute(ddl)
    for ddl in INDEXES + UNIQUE_INDEXES:
        cur.execute(ddl)
    for ddl in VIEWS:
        cur.execute(ddl)
    for sql, rows in SEEDS:
        cur.executemany(sql, rows)

    con.commit()
    cur.execute('PRAGMA foreign_keys = ON')      # 이후 INSERT 부터 FK 검증

    rows = cur.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type DESC, name"
    ).fetchall()
    for kind, name in rows:
        print(f'{kind:5} {name}')
    print(f'\n{sum(1 for k, _ in rows if k == "table")} tables, '
          f'{sum(1 for k, _ in rows if k == "view")} views')
    con.close()


if __name__ == '__main__':
    create_schema()
