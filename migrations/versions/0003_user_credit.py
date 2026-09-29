"""user.credit_krw 추가 - 실제 결제 대신 구매 시 차감하는 시연용 크레딧

기존 회원도 server_default 로 같은 금액을 받는다.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("credit_krw", sa.Integer(), nullable=False, server_default="500000"))
    op.create_check_constraint("ck_user_credit_nonneg", "user", "credit_krw >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_user_credit_nonneg", "user", type_="check")
    op.drop_column("user", "credit_krw")
