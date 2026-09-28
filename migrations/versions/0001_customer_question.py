"""customer_question 테이블 추가 (BE-14)

/ask, /ask/me 질문 기록을 logs/query_log.jsonl 에서 DB 로 옮긴다.
첫 리비전이라 이전 테이블들은 여기서 만들지 않는다 - 그 테이블들은 load_csv.py 가 만든 상태를 전제로 한다.
load_csv.py 로 새로 만든 DB 는 이미 이 테이블이 있으므로 upgrade 대신 `alembic stamp head` 만 한다.

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_question",
        sa.Column("question_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.user_id", ondelete="SET NULL")),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pet.pet_id", ondelete="SET NULL")),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("matched", JSONB(), nullable=False, server_default="[]"),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"),
        ),
    )


def downgrade() -> None:
    op.drop_table("customer_question")
