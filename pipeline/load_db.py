# Last Updated: 2026-08-13
# data/*.csv 의 반려견 더미데이터를 pet_reco.db(SQLite)로 적재하는 스크립트
import csv
import re
import sqlite3
from app.config import DATA_DIR,DB_PATH

# 테이블별 (컬럼명, 타입) 정의. CSV 헤더 순서와 동일해야 하며,
# 이 정의 하나로 CREATE TABLE 문과 값 변환 규칙을 모두 만들어낸다.
#
# 'ID' 는 이 스크립트에서만 쓰는 표시용 타입이다.
# CSV의 'C0001' 처럼 접두어가 붙은 값을 정수 1 로 바꿔 저장하겠다는 뜻이고,
# DDL 로 나갈 때는 INTEGER 가 된다. 접두어는 컬럼명으로 복원 가능해서 정보 손실이 없다.
# SQLite의 INTEGER 는 그 자체로 8바이트(int64)까지 담으며,
# 'INTEGER PRIMARY KEY' 로 정확히 선언해야 rowid 별칭이 되어 별도 인덱스 없이 조회된다.
SCHEMAS = {
    # 보호자(회원) 정보
    'pet_customers': [
        ('customer_id', 'ID PRIMARY KEY'),
        ('name', 'TEXT'),
        ('phone', 'TEXT'),
        ('email', 'TEXT'),
        ('city', 'TEXT'),
        ('account_type', 'TEXT'),  # B2C / B2B
        ('joined_at', 'TEXT'),
    ],
    # 반려견 프로필 - 모든 추천의 출발점이 되는 개인화 정보
    'pet_profiles': [
        ('pet_id', 'ID PRIMARY KEY'),
        ('customer_id', 'ID'),
        ('breed', 'TEXT'),
        ('age', 'INTEGER'),
        ('gender', 'TEXT'),
        ('weight_kg', 'REAL'),
        ('body_type', 'TEXT'),             # 마름 / 표준 / 비만
        ('neutered', 'INTEGER'),           # 중성화 여부(칼로리 산정에 영향)
        ('allergies', 'TEXT'),             # 없음 / 닭고기 / 소고기 / 곡물 / 유제품
        ('feeding_purpose', 'TEXT'),       # 관절 / 다이어트 / 피부 / 없음
        ('diet_preference', 'TEXT'),       # 보통 / 식탐많음 / 식이까다로움
        ('food_form_preference', 'TEXT'),  # 건식 / 습식 / 혼합
        ('budget', 'INTEGER'),
        ('place_type_preference', 'TEXT'),
        ('updated_at', 'TEXT'),
    ],
    # 사료/간식 상품 정보
    'pet_products': [
        ('product_id', 'ID PRIMARY KEY'),
        ('category', 'TEXT'),                 # 사료 / 간식
        ('sub_category', 'TEXT'),             # 건식사료 / 퍼피사료 / 덴탈껌 ...
        ('brand', 'TEXT'),
        ('product_name', 'TEXT'),
        ('price', 'INTEGER'),
        ('weight_g', 'INTEGER'),
        ('target_feeding_purpose', 'TEXT'),   # 관절 / 다이어트 / 피부 / 공용
        ('target_food_form', 'TEXT'),         # 건식 / 습식 / 공용
        ('ingredients', 'TEXT'),              # '|' 로 구분된 원료 목록
        ('tags', 'TEXT'),                     # '|' 로 구분. sub_category + feeding_purpose + 원료 + food_form
        ('description', 'TEXT'),
    ],
    # 구매 이력 + 리뷰. RAG 검색 대상이 되는 핵심 테이블로,
    # 리뷰 작성 시점의 반려견 상태(견종/체급/알레르기 등)가 함께 비정규화되어 있다.
    'pet_purchases': [
        ('purchase_id', 'ID PRIMARY KEY'),
        ('customer_id', 'ID'),
        ('pet_id', 'ID'),
        ('product_id', 'ID'),
        ('category', 'TEXT'),
        ('breed', 'TEXT'),
        ('size_category', 'TEXT'),      # 소형 / 중형 / 대형
        ('weight_kg', 'REAL'),
        ('age_group', 'TEXT'),          # 퍼피 / 성견 / 시니어
        ('age_years', 'REAL'),
        ('allergy', 'TEXT'),            # 리뷰 작성자 반려견의 알레르기(없으면 NULL)
        ('health_condition', 'TEXT'),   # 관절이 약함 / 피부가 예민함 ... (없으면 NULL)
        ('purchased_at', 'TEXT'),
        ('quantity', 'INTEGER'),
        ('rating', 'INTEGER'),
        ('review', 'TEXT'),
        ('is_holdout', 'INTEGER'),      # 1 = 추천 성능 평가용으로 남겨둔 행(임베딩 색인에서 제외)
    ],
}

# 조회 성능용 인덱스. 프로필 조건으로 리뷰를 좁혀 검색하는 경로를 커버한다.
INDEXES = [
    ('idx_profiles_customer', 'pet_profiles(customer_id)'),
    ('idx_purchases_product', 'pet_purchases(product_id)'),
    ('idx_purchases_pet', 'pet_purchases(pet_id)'),
    ('idx_purchases_filter', 'pet_purchases(is_holdout, size_category, age_group)'),
]

def sql_type(col_type):
    """SCHEMAS의 표시용 타입을 실제 DDL 타입으로 바꾼다. 'ID PRIMARY KEY' -> 'INTEGER PRIMARY KEY'"""
    if col_type.startswith('ID'):
        return 'INTEGER' + col_type[2:]
    return col_type


def to_sql_value(raw, col_type):
    """CSV의 문자열 값을 컬럼 타입에 맞게 변환한다. 빈 문자열은 NULL로 저장."""
    raw = raw.strip()
    if raw == '':
        return None
    if col_type.startswith('ID'):
        # 'C0001' -> 1. 접두어가 없거나 형식이 다르면 int()가 터지므로 조용히 넘어가지 않는다.
        return int(re.sub(r'^[A-Za-z]+', '', raw))
    if col_type.startswith('INTEGER'):
        return int(raw)
    if col_type.startswith('REAL'):
        return float(raw)
    return raw


def load_csv(cur, table):
    columns = SCHEMAS[table]
    path = DATA_DIR / f'{table}.csv'

    with open(path, encoding='utf-8-sig') as f:  # utf-8-sig: 파일 앞의 BOM 제거
        reader = csv.DictReader(f)
        expected = [name for name, _ in columns]
        # CSV가 갱신되면서 컬럼이 늘거나 순서가 바뀐 경우를 조용히 넘기지 않고 여기서 잡는다
        if reader.fieldnames != expected:
            raise ValueError(
                f'{table}: CSV 헤더가 스키마와 다릅니다.\n'
                f'  CSV   : {reader.fieldnames}\n'
                f'  스키마: {expected}'
            )
        values = [
            tuple(to_sql_value(row[name], col_type) for name, col_type in columns)
            for row in reader
        ]

    marks = ','.join(['?'] * len(columns))
    cols = ','.join(f'"{name}"' for name, _ in columns)
    cur.executemany(f'INSERT INTO "{table}" ({cols}) VALUES ({marks})', values)
    print(f'{table}: {len(values)} rows')


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    for table in SCHEMAS:
        cur.execute(f'DROP TABLE IF EXISTS "{table}"')  # 재실행 시 중복 방지를 위해 통째로 다시 만든다
        body = ',\n    '.join(f'{name} {sql_type(col_type)}' for name, col_type in SCHEMAS[table])
        cur.execute(f'CREATE TABLE "{table}" (\n    {body}\n)')
        load_csv(cur, table)

    for name, target in INDEXES:
        cur.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {target}')

    con.commit()

    # 적재 결과 요약: 임베딩 대상(is_holdout=0)이 몇 건인지 확인용
    total, holdout = cur.execute(
        'SELECT COUNT(*), SUM(is_holdout) FROM pet_purchases'
    ).fetchone()
    print(f'\n리뷰 {total}건 (색인 대상 {total - holdout}건 / 평가용 holdout {holdout}건)')
    print(f'DB: {DB_PATH}')
    con.close()


if __name__ == '__main__':
    main()
