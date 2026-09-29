"""도메인 CHECK 제약 추가 - 0001년생 펫, 형식이 틀린 날짜, 범위 밖 수치를 DB 가 거절한다

기존 행이 하나라도 조건을 어기면 ADD CONSTRAINT 가 실패하고 전체가 롤백된다(Postgres 는 DDL 도 트랜잭션).
적용 전에 위반 행을 먼저 본다:
    SELECT pet_id, birth_date, created_at FROM pet
     WHERE birth_date !~ '^\\d{4}-\\d{2}-\\d{2}$' OR birth_date < '1990-01-01' OR birth_date > created_at;
    SELECT pet_id, weight_kg FROM pet WHERE weight_kg > 150;
    SELECT user_id, email FROM "user" WHERE email !~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$' OR length(trim(name)) = 0;

값은 app/models/ 의 CheckConstraint 와 같다. 모델을 import 하지 않고 글자로 적는다 -
리비전은 적용된 그 시점의 스키마를 고정해야 해서, 나중에 모델이 바뀌어도 이 파일은 안 바뀌어야 한다.
load_csv.py 로 새로 만든 DB 는 이미 이 제약이 있으므로 upgrade 대신 `alembic stamp head` 만 한다.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DATE_RE = r"'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$'"
DATETIME_RE = r"'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]) ([01]\d|2[0-3]):[0-5]\d:[0-5]\d$'"

# 새로 거는 제약: (이름, 테이블, 조건)
ADDED = [
    ("ck_user_name", "user", "length(trim(name)) > 0"),
    ("ck_user_email", "user", r"email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'"),
    ("ck_user_created_at", "user", f"created_at ~ {DATETIME_RE}"),
    ("ck_user_updated_at", "user", f"updated_at ~ {DATETIME_RE} AND updated_at >= created_at"),
    ("ck_user_last_login_at", "user", f"last_login_at ~ {DATETIME_RE} AND last_login_at >= created_at"),
    ("ck_user_withdrawn_at", "user", f"withdrawn_at ~ {DATETIME_RE} AND withdrawn_at >= created_at"),
    ("ck_pet_name", "pet", "length(trim(name)) > 0"),
    (
        "ck_pet_birth_date",
        "pet",
        f"birth_date ~ {DATE_RE} AND birth_date >= '1990-01-01' AND birth_date <= created_at",
    ),
    ("ck_pet_inactive_at", "pet", f"inactive_at ~ {DATETIME_RE} AND inactive_at >= created_at"),
    ("ck_pet_created_at", "pet", f"created_at ~ {DATETIME_RE}"),
    ("ck_pet_updated_at", "pet", f"updated_at ~ {DATETIME_RE} AND updated_at >= created_at"),
    ("ck_pet_survey_created_at", "pet_survey", f"created_at ~ {DATETIME_RE}"),
    ("ck_product_brand", "product", "length(trim(brand)) > 0"),
    ("ck_product_name", "product", "length(trim(name)) > 0"),
    ("ck_product_created_at", "product", f"created_at ~ {DATETIME_RE}"),
    ("ck_product_updated_at", "product", f"updated_at ~ {DATETIME_RE} AND updated_at >= created_at"),
    (
        "ck_nutrition_proximate_sum",
        "product_nutrition",
        "COALESCE(crude_protein_pct, 0) + COALESCE(crude_fat_pct, 0) + COALESCE(crude_fiber_pct, 0)"
        " + COALESCE(crude_ash_pct, 0) + COALESCE(moisture_pct, 0) <= 101",
    ),
    ("ck_purchase_purchased_at", "purchase", f"purchased_at ~ {DATETIME_RE}"),
    ("ck_review_reviewed_at", "review", f"reviewed_at ~ {DATETIME_RE}"),
]

# 상한을 더해 바꾸는 제약: (이름, 테이블, 새 조건, 옛 조건)
TIGHTENED = [
    ("ck_pet_weight_kg", "pet", "weight_kg > 0 AND weight_kg <= 150", "weight_kg > 0"),
    (
        "ck_product_kcal_per_100g",
        "product",
        "kcal_per_100g > 0 AND kcal_per_100g <= 900",
        "kcal_per_100g > 0",
    ),
    (
        "ck_product_target_age_max_month",
        "product",
        "target_age_max_month BETWEEN 0 AND 1200",
        "target_age_max_month >= 0",
    ),
    (
        "ck_purchase_age_month_at_purchase",
        "purchase",
        "age_month_at_purchase BETWEEN 0 AND 360",
        "age_month_at_purchase >= 0",
    ),
]


def upgrade() -> None:
    for name, table, cond in ADDED:
        op.create_check_constraint(name, table, cond)
    for name, table, new, _old in TIGHTENED:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, new)


def downgrade() -> None:
    for name, table, _new, old in TIGHTENED:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, old)
    for name, table, _cond in reversed(ADDED):
        op.drop_constraint(name, table, type_="check")
