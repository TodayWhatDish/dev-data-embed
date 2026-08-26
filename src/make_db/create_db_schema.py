# Last Updated: 2026-08-13
"""
'오늘 뭐먹냥' user.db 스키마 (1단계 — 추천 경로).

설계 규칙
  1) 모든 PK 는 INTEGER PRIMARY KEY (SQLite rowid 별칭).
     - 테이블 B-tree 가 정수로 직접 키잉되어 별도 인덱스가 생기지 않는다.
     - 조인이 문자열 비교가 아니라 64비트 정수 비교가 된다.
     - SQLite 에 unsigned 타입은 없다. uint32/uint64 는 STRICT 에서 에러이고,
       비STRICT 에서도 그냥 INTEGER 로 해석될 뿐 아무 제약이 없다.
       INTEGER 는 값 크기에 따라 1~8바이트로 가변 저장되므로 폭 지정도 무의미하다.

  2) 다대다 연결 테이블도 대리키(INTEGER PK) + 자연키 UNIQUE 인덱스로 통일한다.
     행 하나를 단일 값으로 참조할 수 있어 API/ORM 에서 다루기 쉽다.

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

실행: python src/make_db/create_db_schema.py   (repo root 에서)
"""

import sqlite3

DB_PATH = 'user.db'

# 전 테이블 STRICT. 타입 강제는 이 스키마의 전제이므로 끄는 스위치를 두지 않는다.
STRICT = ' STRICT'


# ===========================================================================
# A. 보호자 / 반려견
# ===========================================================================

TABLES = [

# ---------------------------------------------------------------------------
# Comment: 서비스 가입자(보호자) 계정. 반려견·구매·리뷰의 최상위 소유자이며,
#          삭제 시 하위 데이터가 함께 정리된다(ON DELETE CASCADE).
#          상태 컬럼을 두지 않는다 — '휴면'은 last_login_at 에서 계산되는 파생값이라
#          컬럼으로 굳히면 휴면 기준 정책이 바뀔 때마다 전 행을 갱신해야 한다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE users (
    user_id       INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키. rowid 별칭이라 조회/조인이 가장 빠르다.
        --       하위 테이블(pets/purchases/reviews)이 참조하는 소유자 키는 오직 이 값이다.
        --       외부 인증 ID(auth_uid)를 FK 로 쓰지 않는 이유는 아래 auth_uid 주석 참고.
    auth_provider TEXT    NOT NULL DEFAULT 'google'
                          CHECK (auth_provider IN ('google', 'firebase', 'kakao', 'apple', 'local')),
        -- desc: 신원을 확인해 준 주체. 현재 구글 로그인만 쓴다.
        --       Firebase Auth 를 경유하면 'firebase'(uid 는 Firebase UID),
        --       구글 OAuth 를 직접 붙이면 'google'(uid 는 ID token 의 sub)이다.
        --       CHECK 목록에 미사용 값을 미리 넣어둔 이유: SQLite 는 CHECK 를 바꾸려면
        --       테이블을 재생성해야 한다. 값을 넓게 잡아두는 건 공짜고, 안 쓰면 그만이다.
    auth_uid      TEXT    NOT NULL,
        -- desc: 제공자가 준 불변 고유 ID. 이메일이 아니라 이 값으로 계정을 찾는다 —
        --       이메일은 사용자가 바꿀 수 있지만 이 값은 안 바뀐다.
        --       로그인 순간에만 읽힌다. 로그인 이후 요청은 토큰에서 복원한 user_id 만 쓴다.
        --       하위 테이블이 이 컬럼을 참조하면 (1) 조인이 문자열 비교가 되어 느려지고
        --       (2) 인증 방식을 바꿀 때 전 테이블을 갱신해야 하므로, 참조는 user_id 로만 한다.
    email         TEXT    NOT NULL UNIQUE,
        -- desc: 연락/표시용 이메일. 구글은 항상 검증된 이메일을 주므로 NOT NULL 이 성립한다.
        --       이메일을 안 주거나 미검증으로 주는 제공자(카카오는 선택 동의)를 붙이는 날
        --       이 제약은 반드시 완화해야 한다. 로그인 식별자는 auth_uid 지 이 컬럼이 아니다.
    name          TEXT    NOT NULL,
        -- desc: 보호자 이름(표시용).
    phone         TEXT,
        -- desc: 연락처. UNIQUE 를 걸지 않는다 — 가족 공유, 통신사 번호 재할당,
        --       탈퇴 후 재가입 때문에 실제로 유일하지 않다. 로그인 수단도 아니다.
    region        TEXT,
        -- desc: 활동 지역(시/도). 명소 추천(3단계)과 배송권역에 쓰인다.
    account_type  TEXT    NOT NULL DEFAULT 'B2C'
                          CHECK (account_type IN ('B2C', 'B2B')),
        -- desc: 일반 보호자(B2C) / 업체(B2B). 현재는 B2C 전용이나 GOAL 상 타겟에 업체가 있어 남긴다.
    last_login_at TEXT    CHECK (last_login_at IS NULL OR datetime(last_login_at) IS NOT NULL),
        -- desc: 마지막 로그인 시각. '휴면 계정'은 이 값에서 계산한다(저장하지 않는다).
    withdrawn_at  TEXT    CHECK (withdrawn_at IS NULL OR datetime(withdrawn_at) IS NOT NULL),
        -- desc: 탈퇴 시각. NULL = 활성. 불리언 is_del 대신 시각을 저장하는 이유는
        --       개인정보 보관기간 경과분 파기 배치가 '언제 탈퇴했는지'를 필요로 하기 때문이다.
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
        -- desc: 가입 시각. 인덱스는 걸지 않는다 — 범위 조회 수요가 생긴 뒤에 추가한다.
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        -- desc: 마지막 수정 시각.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 견종 마스터. 견종명을 각 테이블에 문자열로 박으면 표기가 반드시 갈리므로
#          (실제 CSV 에서 '푸들'/'토이푸들', '코카스파니엘'/'코커스패니얼' 혼재)
#          한 곳에 모으고 나머지는 breed_id 로 참조한다. 정적 코드표에 가깝다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE breeds (
    breed_id           INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    name_ko            TEXT    NOT NULL UNIQUE,
        -- desc: 표준 견종명(한글). 앱에서는 드롭다운으로 선택시켜 표기 흔들림을 원천 차단한다.
    size_category      TEXT    NOT NULL CHECK (size_category IN ('소형', '중형', '대형')),
        -- desc: 체구 분류. 제품의 target_size 와 매칭되는 1차 필터.
    adult_weight_min_kg REAL   CHECK (adult_weight_min_kg > 0),
        -- desc: 성견 표준체중 하한. 입력 체중이 견종 범위를 벗어나면 비만/저체중 판단 근거가 된다.
    adult_weight_max_kg REAL   CHECK (adult_weight_max_kg > 0)
        -- desc: 성견 표준체중 상한.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 반려견 프로필. 추천의 정형 입력 전부가 여기 모인다.
#          원칙: '오래 변하지 않는 속성'만 넣는다. 그때그때 달라지는 상태
#          ("요즘 변이 무르다")는 요청 단위 자연어로 받고 프로필에 저장하지 않는다.
#          프로필에 두면 다음 입력이 이전 값을 덮어써서 이력이 사라지기 때문이다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE pets (
    pet_id               INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    user_id              INTEGER NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
        -- desc: 보호자. 1 보호자 : N 반려견.
    name                 TEXT    NOT NULL,
        -- desc: 반려견 이름. LLM 응답에서 이름을 불러주는 데 쓴다.
    breed_id             INTEGER
        REFERENCES breeds(breed_id) ON DELETE SET NULL,
        -- desc: 견종. 믹스견/모름을 허용해야 하므로 NULL 가능.
    birth_date           TEXT    CHECK (birth_date IS NULL OR date(birth_date) IS NOT NULL),
        -- desc: 생년월일. age 정수를 저장하지 않는 이유는 시간이 지나면 조용히 틀려지기 때문이다.
        --       나이는 조회 시점에 계산한다.
    gender               TEXT    CHECK (gender IN ('M', 'F')),
        -- desc: 성별.
    neutered             INTEGER CHECK (neutered IN (0, 1)),
        -- desc: 중성화 여부. 값은 입력받아 보관한다.
        --       [주의] 급여/추천 로직의 입력으로는 쓰지 않는다(2026-08-13 팀 협의).
        --       중성화가 기초대사량을 낮추는 건 사실이나 개체차가 커서 0/1 로 정도를 표현할 수 없고,
        --       '살이 찌기 쉽다'는 결과는 body_type 이 이미 더 직접적으로 담고 있다.
        --       정도 차이가 중요한 경우는 보호자가 요청 자연어로 말하는 쪽이 정확하다.
        --       보관하는 이유는 프로필 완성도와, 향후 코호트 분석(중성화군 체형 분포) 때문이다.
    weight_kg            REAL    CHECK (weight_kg > 0),
        -- desc: 현재 체중. 급여량·칼로리 판단과 제품 용량 추천의 기준.
    body_type            TEXT    CHECK (body_type IN ('마름', '표준', '비만')),
        -- desc: 체형(보호자 관찰값). 다이어트 제품 추천의 가장 직접적인 신호.
    diet_preference      TEXT    CHECK (diet_preference IN ('보통', '식탐많음', '식이까다로움')),
        -- desc: 식성. '식이까다로움'이면 기호성 지표를 우선 정렬한다.
    food_form_preference TEXT    CHECK (food_form_preference IN ('건식', '습식', '혼합')),
        -- desc: 선호 형태. products.food_form 과 매칭.
    monthly_budget_krw   INTEGER CHECK (monthly_budget_krw > 0),
        -- desc: 월 예산(원). 총액이 아니라 products.price_per_100g 로 환산 비교해야 정확하다.
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
        -- desc: 등록 시각.
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now'))
        -- desc: 마지막 수정 시각. 체중/체형이 갱신될 때마다 올라간다.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 알러지원 마스터. 반려견의 알러지(pet_allergies)와 제품 원료(ingredients)를
#          잇는 공통 어휘. 양쪽이 같은 ID 를 참조해야 '이 제품에 이 개의 알러지원이
#          들어있는가'를 문자열 매칭 없이 조인으로 판정할 수 있다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE allergens (
    allergen_id   INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    name_ko       TEXT    NOT NULL UNIQUE,
        -- desc: 알러지원 표준명. 예: '닭고기', '소고기', '곡물', '유제품'.
    allergen_type TEXT    CHECK (allergen_type IN ('단백질', '곡물', '유제품', '첨가물', '기타'))
        -- desc: 분류. 교차반응 안내와 대체 단백질 제안에 쓴다.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 반려견별 알러지 등록. 추천의 '하드 필터' 입력이다.
#          보호자가 알러지를 안다는 것 자체가 이미 겪어봤다는 뜻이므로 심각도를 나누지 않고
#          무조건 배제한다 — 반쯤 아는 심각도로 필터 강도를 조절하는 게 가장 위험하다.
#          그래서 severity / is_confirmed / source 컬럼을 두지 않는다.
#          [중요] 리뷰에서 추론한 알러지를 이 테이블에 넣으면 안 된다.
#          추론값이 섞이면 안전한 제품이 잘못 배제되고, 보호자가 그 값을 사실로 믿는다.
#          추론 결과는 리뷰 쪽(2단계 review_signals)에만 남기고 프로필로 승격시키지 않는다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE pet_allergies (
    pet_allergy_id INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키. 모든 테이블을 정수 PK 로 통일해 행 하나를 단일 값으로 참조한다.
    pet_id         INTEGER NOT NULL
        REFERENCES pets(pet_id) ON DELETE CASCADE,
        -- desc: 대상 반려견.
    allergen_id    INTEGER NOT NULL
        REFERENCES allergens(allergen_id) ON DELETE RESTRICT,
        -- desc: 알러지원. 마스터에서 참조 중이면 삭제를 막는다(RESTRICT).
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        -- desc: 보호자가 등록한 시각. 진단일이 아니다 — 보호자가 정확한 발병일을 알 수 없다.
){STRICT}
''',


# ===========================================================================
# B. 제품
# ===========================================================================

# ---------------------------------------------------------------------------
# Comment: 급여목적 마스터(관절/다이어트/피부 등). GOAL 의 '급여목적'.
#          반려견 쪽에는 두지 않는다 — 목적은 프로필 속성이 아니라 요청 속성이라서
#          (이번 달은 다이어트, 다음 달은 피부) 프로필에 박으면 계속 낡는다.
#          보호자의 목적은 요청 자연어에서 뽑고, 제품 쪽만 정형으로 관리한다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE feeding_purposes (
    feeding_purpose_id INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    name_ko            TEXT    NOT NULL UNIQUE,
        -- desc: 목적명(한글). 예: '관절', '다이어트', '피부', '치아', '신장'.
    code               TEXT    UNIQUE
        -- desc: 코드값(joint, diet, skin...). 애플리케이션 분기·i18n 용.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 판매 제품(사료/간식). 추천 후보 집합의 원본.
#          브랜드는 별도 테이블로 분리하지 않고 텍스트 컬럼으로 둔다 — 자체 판매 B2C 구조라
#          브랜드별 정산/제휴 관리가 없기 때문. 필요해지면 그때 brands 로 분리한다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE products (
    product_id       INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    brand            TEXT    NOT NULL,
        -- desc: 브랜드명.
    category         TEXT    NOT NULL CHECK (category IN ('사료', '간식')),
        -- desc: 대분류.
    sub_category     TEXT,
        -- desc: 소분류. 예: '건식사료', '덴탈껌', '동결건조간식'.
    name             TEXT    NOT NULL,
        -- desc: 제품명.
    food_form        TEXT    CHECK (food_form IN ('건식', '습식', '동결건조', '생식', '공용')),
        -- desc: 급여 형태. pets.food_form_preference 와 매칭.
    price_krw        INTEGER NOT NULL CHECK (price_krw >= 0),
        -- desc: 판매가(원).
    weight_g         INTEGER NOT NULL CHECK (weight_g > 0),
        -- desc: 내용량(g).
    price_per_100g   INTEGER GENERATED ALWAYS AS (price_krw * 100 / weight_g) STORED,
        -- desc: 100g당 단가. 예산 비교의 실제 기준 — 1.8kg 3만원과 5kg 6만원을
        --       총액으로 비교하면 틀린다. 생성 컬럼이라 값이 어긋날 수 없다.
    kcal_per_100g    INTEGER CHECK (kcal_per_100g > 0),
        -- desc: 100g당 열량. 중성화·체형과 묶여 급여량/칼로리 판단을 성립시킨다.
    target_size      TEXT    CHECK (target_size IN ('소형', '중형', '대형', '전체')),
        -- desc: 권장 체구. breeds.size_category 와 매칭.
    target_age_group TEXT    CHECK (target_age_group IN ('퍼피', '성견', '시니어', '전체')),
        -- desc: 권장 연령대. pets.birth_date 에서 계산한 나이와 매칭.
    description      TEXT,
        -- desc: 제품 설명. 후기가 없는 신규 제품(콜드스타트)의 임베딩 대상.
    ingredients_verified INTEGER NOT NULL DEFAULT 0
                         CHECK (ingredients_verified IN (0, 1)),
        -- desc: 원료표를 사람이 확인해 product_ingredients 에 빠짐없이 등록했는가.
        --       0 = 미확인(기본값). 알러지 판정을 '안전/위험' 2분법으로 두면
        --       원료가 등록되지 않은 제품이 NOT EXISTS 를 그냥 통과해 '안전'이 된다.
        --       즉 데이터가 부실할수록 더 안전해 보이는, 방향이 반대인 실패가 생긴다.
        --       이 플래그가 그 사이에 '판정불가'를 만들어 조용한 통과를 막는다.
        --       기본값이 0 이므로 신규 등록 제품은 자동으로 판정불가에서 시작하고,
        --       원료를 확인한 사람만 1 로 올린다. (v_product_safety 참조)
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        -- desc: 판매중 여부. 단종 제품을 지우면 과거 구매/리뷰가 끊기므로 플래그로 내린다.
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
        -- desc: 등록 시각.
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        -- desc: 마지막 수정 시각.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 제품 ↔ 급여목적 (다대다). 제품 하나가 '관절 + 다이어트'처럼 복수 목적을 갖는다.
#          목적명을 여기 문자열로 중복 저장하지 않고 feeding_purposes 를 참조한다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE product_feeding_purposes (
    product_feeding_purpose_id INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    product_id                 INTEGER NOT NULL
        REFERENCES products(product_id) ON DELETE CASCADE,
        -- desc: 제품.
    feeding_purpose_id         INTEGER NOT NULL
        REFERENCES feeding_purposes(feeding_purpose_id) ON DELETE RESTRICT
        -- desc: 급여목적.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 제품 영양성분(보장성분표). products 와 1:1 이지만 분리하는 이유는 결측 때문 —
#          사료는 성분표가 있고 간식은 없는 경우가 흔해서, products 에 NULL 컬럼 8개가
#          늘어서는 것보다 '값이 있는 제품만 행이 있는' 형태가 깔끔하다.
#          태그 문자열로는 "인 함량 낮은 사료"를 고를 수 없다 — 수치가 있어야 한다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE product_nutrition (
    product_id        INTEGER NOT NULL PRIMARY KEY
        REFERENCES products(product_id) ON DELETE CASCADE,
        -- desc: 제품. 1:1 이므로 FK 가 곧 PK.
    crude_protein_pct REAL CHECK (crude_protein_pct BETWEEN 0 AND 100),
        -- desc: 조단백(%). 신장 관리식 판정(고단백 회피)의 핵심 지표.
    crude_fat_pct     REAL CHECK (crude_fat_pct BETWEEN 0 AND 100),
        -- desc: 조지방(%). 다이어트/췌장 이슈 판정.
    crude_fiber_pct   REAL CHECK (crude_fiber_pct BETWEEN 0 AND 100),
        -- desc: 조섬유(%). 포만감·배변 상태와 연결된다.
    moisture_pct      REAL CHECK (moisture_pct BETWEEN 0 AND 100),
        -- desc: 수분(%). 건식/습식 구분의 실제 근거.
    calcium_pct       REAL CHECK (calcium_pct BETWEEN 0 AND 100),
        -- desc: 칼슘(%). 퍼피 성장기 골격 형성.
    phosphorus_pct    REAL CHECK (phosphorus_pct BETWEEN 0 AND 100),
        -- desc: 인(%). 신장 관리식은 인을 제한한다.
    sodium_pct        REAL CHECK (sodium_pct BETWEEN 0 AND 100)
        -- desc: 나트륨(%). 심장/신장 관리 시 제한 대상.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 원료 마스터. allergen_id 가 이 스키마에서 가장 중요한 연결 고리다.
#          이게 없으면 '닭가슴살', '계육분', '치킨오일'을 닭 알러지견에게 그대로 추천하게 된다.
#          원료명 문자열 비교로는 절대 잡히지 않는다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE ingredients (
    ingredient_id INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    name_ko       TEXT    NOT NULL UNIQUE,
        -- desc: 원료명. 예: '닭가슴살', '계육분', '연어', '귀리'.
    allergen_id   INTEGER
        REFERENCES allergens(allergen_id) ON DELETE SET NULL
        -- desc: 이 원료가 속하는 알러지원. NULL = 알러지와 무관한 원료.
        --       '닭가슴살'·'계육분'·'치킨오일'이 모두 '닭고기' 한 ID 를 가리키게 하는 것이 목적.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 제품 ↔ 원료 (다대다). 알러지 배제 필터가 실제로 조인하는 테이블.
#          배합 순서(position)나 주단백질 여부는 두지 않는다 — 판정을 '포함/미포함' 이진으로
#          단순화하는 것이 안전하고, 순서 데이터 확보도 현실적으로 어렵다.
#          알러지원이 하나라도 포함되면 후보에서 제외한다(부분 감점이 아니라 배제).
# ---------------------------------------------------------------------------
f'''
CREATE TABLE product_ingredients (
    product_ingredient_id INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    product_id            INTEGER NOT NULL
        REFERENCES products(product_id) ON DELETE CASCADE,
        -- desc: 제품.
    ingredient_id         INTEGER NOT NULL
        REFERENCES ingredients(ingredient_id) ON DELETE RESTRICT
        -- desc: 원료.
){STRICT}
''',


# ===========================================================================
# C. 구매 / 후기 — 학습·검색 데이터
# ===========================================================================

# ---------------------------------------------------------------------------
# Comment: 구매 이력. 재구매 여부는 컬럼으로 저장하지 않는다 —
#          (user_id, product_id, purchased_at) 만으로 SQL 계산이 되므로
#          별도 플래그나 이전구매 FK 를 두면 정합성 관리 대상만 늘어난다.
#          재구매는 별점보다 강한 만족 신호다(돈을 다시 쓴 행동). 랭킹 가중치와
#          "비슷한 프로필 보호자 중 N% 재구매" 문구의 근거가 된다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE purchases (
    purchase_id    INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    user_id        INTEGER NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
        -- desc: 구매자.
    pet_id         INTEGER NOT NULL
        REFERENCES pets(pet_id) ON DELETE CASCADE,
        -- desc: 누구에게 급여하려고 샀는지. 프로필별 취향 학습의 연결점.
    product_id     INTEGER NOT NULL
        REFERENCES products(product_id) ON DELETE RESTRICT,
        -- desc: 구매 제품. 과거 이력이 끊기면 안 되므로 삭제를 막는다.
    purchased_at   TEXT    NOT NULL CHECK (date(purchased_at) IS NOT NULL),
        -- desc: 구매일. 재구매 주기 계산의 기준.
    quantity       INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
        -- desc: 수량.
    unit_price_krw INTEGER NOT NULL CHECK (unit_price_krw >= 0),
        -- desc: 구매 시점 단가. products.price_krw 가 나중에 바뀌어도 당시 금액이 남는다.
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        -- desc: 레코드 생성 시각.
){STRICT}
''',

# ---------------------------------------------------------------------------
# Comment: 구매 후기. RAG 검색의 대상이자 이 프로젝트의 핵심 자산.
#          purchases 와 분리하는 이유가 두 가지다.
#            (1) 후기 없는 구매가 실제로는 다수인데, 한 테이블이면 표현할 수 없다.
#            (2) 구매 시점과 작성 시점이 다르다 — 급여 2주 뒤 후기와 당일 후기는
#                신뢰도가 다르고, 그 차이는 두 날짜가 따로 있어야 계산된다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE reviews (
    review_id   INTEGER NOT NULL PRIMARY KEY,
        -- desc: 대리키.
    purchase_id INTEGER NOT NULL UNIQUE
        REFERENCES purchases(purchase_id) ON DELETE CASCADE,
        -- desc: 대상 구매. 구매 1건당 후기 1건이므로 UNIQUE.
    pet_id      INTEGER NOT NULL
        REFERENCES pets(pet_id) ON DELETE CASCADE,
        -- desc: 후기 대상 반려견. purchases 에서 유도 가능하지만,
        --       검색 시 매번 조인하지 않도록 의도적으로 중복 보관한다.
    product_id  INTEGER NOT NULL
        REFERENCES products(product_id) ON DELETE RESTRICT,
        -- desc: 후기 대상 제품. 같은 이유로 중복 보관.
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
        -- desc: 별점.
    content     TEXT    NOT NULL,
        -- desc: 후기 본문(한국어 자유 텍스트). 임베딩 대상이자 근거 인용의 원문.
    written_at  TEXT    NOT NULL CHECK (date(written_at) IS NOT NULL),
        -- desc: 작성일.
    is_holdout  INTEGER NOT NULL DEFAULT 0 CHECK (is_holdout IN (0, 1)),
        -- desc: 평가셋 분리 플래그. 1 인 행은 임베딩/검색에서 제외하고
        --       추천 정확도 측정에만 쓴다. 학습에 섞이면 성능이 부풀려진다.
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        -- desc: 레코드 생성 시각.
){STRICT}
''',


# ===========================================================================
# D. 임베딩
# ===========================================================================

# ---------------------------------------------------------------------------
# Comment: 후기 임베딩 벡터. SQLite 에 벡터 타입이 없어 float32 원시 바이트를 BLOB 으로 넣는다.
#          JSON 문자열 대비 384차원 기준 약 4.5KB -> 1.5KB 로 줄고 파싱 비용이 사라진다.
#          normalize 된 벡터를 저장하므로 코사인 유사도가 내적으로 계산된다.
# ---------------------------------------------------------------------------
f'''
CREATE TABLE review_embeddings (
    review_id  INTEGER NOT NULL PRIMARY KEY
        REFERENCES reviews(review_id) ON DELETE CASCADE,
        -- desc: 대상 후기. 1:1 이므로 FK 가 곧 PK.
    model      TEXT    NOT NULL,
        -- desc: 임베딩 모델명. 예: 'paraphrase-multilingual-MiniLM-L12-v2'.
        --       모델을 바꾸면 벡터 공간이 달라져 기존 벡터와 비교가 불가능하므로 반드시 남긴다.
    dim        INTEGER NOT NULL CHECK (dim > 0),
        -- desc: 차원 수. BLOB 을 numpy 로 복원할 때 필요하다.
    vector     BLOB    NOT NULL,
        -- desc: float32 벡터 원시 바이트. np.asarray(v, 'float32').tobytes().
    doc        TEXT    NOT NULL,
        -- desc: 실제로 임베딩한 문서 원문(카테고리·프로필 컨텍스트 + 후기).
        --       문서 조립 방식을 바꿨을 때 무엇이 달라졌는지 추적하는 재현성 장치.
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        -- desc: 생성 시각. 재임베딩 대상 선별에 쓴다.
){STRICT}
''',
]


# ===========================================================================
# 인덱스 — 원칙: FK 컬럼에는 건다(조인 + 부모행 삭제 검사에 매번 쓰임).
#              나머지는 느린 쿼리를 관측한 뒤에 추가한다.
#              인덱스는 쓰기 비용과 공간을 '항상' 지불하고 읽기 이득은 '조건부'다.
# ===========================================================================

INDEXES = [
    # -- FK 조인용 --------------------------------------------------------
    # [주의] 연결 테이블(pet_allergies, product_feeding_purposes, product_ingredients)의
    #        부모 FK 에는 여기서 인덱스를 만들지 않는다.
    #        아래 UNIQUE_INDEXES 의 복합 인덱스가 선두 컬럼(pet_id / product_id)으로
    #        시작하므로, leftmost prefix 규칙에 따라 그 인덱스가 단일 컬럼 조회에도 그대로 쓰인다.
    #        따로 만들면 같은 인덱스를 두 벌 유지하는 셈이라 쓰기 비용만 늘어난다.
    'CREATE INDEX idx_pets_user            ON pets(user_id)',
    'CREATE INDEX idx_pets_breed           ON pets(breed_id)',
    'CREATE INDEX idx_purchases_user       ON purchases(user_id)',
    'CREATE INDEX idx_purchases_pet        ON purchases(pet_id)',
    'CREATE INDEX idx_purchases_product    ON purchases(product_id)',
    'CREATE INDEX idx_reviews_pet          ON reviews(pet_id)',
    'CREATE INDEX idx_reviews_product      ON reviews(product_id, rating)',

    # -- 역방향 조회: "이 알러지원을 가진 제품 전부" (배제 필터가 이 방향으로 탄다) --
    'CREATE INDEX idx_ingredients_allergen ON ingredients(allergen_id)',
    'CREATE INDEX idx_prod_ing_ingredient  ON product_ingredients(ingredient_id)',
    'CREATE INDEX idx_pet_allergies_allergen ON pet_allergies(allergen_id)',
    'CREATE INDEX idx_prod_fp_purpose      ON product_feeding_purposes(feeding_purpose_id)',

    # -- 후보군 1차 필터 --------------------------------------------------
    'CREATE INDEX idx_products_filter      ON products(is_active, category, target_size, target_age_group)',
    'CREATE INDEX idx_products_ppg         ON products(price_per_100g)',

    # -- 평가셋 분리 -------------------------------------------------------
    'CREATE INDEX idx_reviews_holdout      ON reviews(is_holdout)',
]


# ===========================================================================
# UNIQUE 인덱스 — 중복 등록 방지. 대리키 PK 와 별개로 '자연키'를 여기서 강제한다.
#
# 컬럼 순서는 (부모, 자식) 순으로 둔다. 이 순서라야 인덱스 하나가 두 가지 일을 겸한다.
#   (1) 중복 등록 차단          : UNIQUE(pet_id, allergen_id)
#   (2) 부모 기준 조회 가속      : WHERE pet_id = ?  <- leftmost prefix 로 그대로 탄다
# 반대 순서로 두면 (2)를 위해 인덱스를 하나 더 만들어야 한다.
# ===========================================================================

UNIQUE_INDEXES = [
    # 같은 외부 계정이 두 유저에 붙는 것을 DB 레벨에서 차단한다.
    # 로그인 처리는 이 인덱스를 그대로 타는 조회 하나로 끝난다:
    #   SELECT user_id FROM users WHERE auth_provider = ? AND auth_uid = ?
    # (부모, 자식) 순서 규칙에 맞춰 provider 를 앞에 둔다.
    'CREATE UNIQUE INDEX uq_users_auth     ON users(auth_provider, auth_uid)',

    # 같은 반려견에 같은 알러지원을 두 번 등록할 수 없다.
    'CREATE UNIQUE INDEX uq_pet_allergen   ON pet_allergies(pet_id, allergen_id)',
    'CREATE UNIQUE INDEX uq_product_feeding_purpose ON product_feeding_purposes(product_id, feeding_purpose_id)',
    'CREATE UNIQUE INDEX uq_product_ingredient ON product_ingredients(product_id, ingredient_id)',
]


# ===========================================================================
# 뷰
# ===========================================================================

VIEWS = [
    # Comment: 반려견 1행 요약. LLM 프롬프트에 넣을 정형 컨텍스트를 한 번에 뽑는다.
    #          나이를 저장하지 않고 birth_date 에서 계산하는 지점이 여기다.
    '''
CREATE VIEW v_pet_context AS
SELECT
    p.pet_id,
    p.user_id,
    p.name,
    b.name_ko                                   AS breed,
    b.size_category,
    CAST((julianday('now') - julianday(p.birth_date)) / 365.25 AS INTEGER) AS age_years,
    p.gender,
    p.neutered,
    p.weight_kg,
    p.body_type,
    p.diet_preference,
    p.food_form_preference,
    p.monthly_budget_krw,
    (SELECT group_concat(a.name_ko, ',')
       FROM pet_allergies pa JOIN allergens a ON a.allergen_id = pa.allergen_id
      WHERE pa.pet_id = p.pet_id)               AS allergens
FROM pets p
LEFT JOIN breeds b ON b.breed_id = p.breed_id
''',

    # Comment: 임베딩 문서 조립. embed 스크립트는 이 뷰를 SELECT 해서 doc 을 그대로 쓴다.
    #          후기 본문만 넣지 않고 제품 분류와 반려견 컨텍스트를 앞에 붙이는 이유는,
    #          같은 "잘 먹어요"라도 소형견 퍼피의 습식과 대형견 시니어의 건식은 다른 정보이기 때문.
    #          is_holdout = 1 은 평가셋이므로 제외한다.
    '''
CREATE VIEW v_review_docs AS
SELECT
    r.review_id,
    r.product_id,
    r.pet_id,
    pr.sub_category || '/' || COALESCE(b.size_category, '미상')
        || ' ' || COALESCE(pt.body_type, '')
        || ' 후기: ' || r.content              AS doc
FROM reviews  r
JOIN products pr ON pr.product_id = r.product_id
JOIN pets     pt ON pt.pet_id     = r.pet_id
LEFT JOIN breeds b ON b.breed_id  = pt.breed_id
WHERE r.is_holdout = 0
''',

    # Comment: 반려견 × 제품 알러지 판정. 추천 파이프라인의 첫 단계.
    #          알러지 배제를 LLM 이 아니라 SQL 이 하는 이유는 결정성 때문이다 —
    #          LLM 은 확률적으로 실패하지만 NOT EXISTS 는 반드시 배제한다.
    #          판정은 2분법이 아니라 3분법이다. '안전'과 '위험' 사이에 '판정불가'를 둔다.
    #            위험     : 알러지원이 확인됨 -> 후보에서 완전히 제외(감점이 아니다)
    #            판정불가 : 원료를 확인한 적이 없음 -> 모르는 것을 안전으로 처리하지 않는다
    #            안전     : 원료 확인 완료 + 알러지원 없음
    #          '판정불가'가 없으면 원료 미등록 제품이 조용히 '안전'으로 통과한다.
    '''
CREATE VIEW v_product_safety AS
SELECT
    pt.pet_id,
    pr.product_id,
    CASE
        WHEN EXISTS (
                SELECT 1
                FROM product_ingredients pi
                JOIN ingredients   i  ON i.ingredient_id = pi.ingredient_id
                JOIN pet_allergies pa ON pa.allergen_id  = i.allergen_id
               WHERE pi.product_id = pr.product_id
                 AND pa.pet_id     = pt.pet_id
             ) THEN '위험'
        WHEN pr.ingredients_verified = 0 THEN '판정불가'
        ELSE '안전'
    END AS verdict
FROM pets pt
CROSS JOIN products pr
WHERE pr.is_active = 1
''',

    # Comment: 추천 후보군. v_product_safety 에서 '안전'만 통과시킨다.
    #          '판정불가'를 후보에 넣고 경고를 붙이는 정책으로 바꾸려면 이 뷰만 고치면 되고,
    #          판정 로직 자체는 v_product_safety 한 곳에만 있다.
    '''
CREATE VIEW v_safe_products AS
SELECT pet_id, product_id
FROM v_product_safety
WHERE verdict = '안전'
''',
]


# DROP 순서는 FK 역순 (자식 -> 부모)
DROP_VIEWS = ['v_safe_products', 'v_product_safety', 'v_review_docs', 'v_pet_context']
DROP_TABLES = [
    'review_embeddings',
    'reviews', 'purchases',
    'product_ingredients', 'ingredients',
    'product_nutrition', 'product_feeding_purposes', 'products', 'feeding_purposes',
    'pet_allergies', 'allergens',
    'pets', 'breeds', 'users',
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
