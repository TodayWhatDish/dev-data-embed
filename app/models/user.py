# 계정 ORM 모델. 스키마 정의는 pipeline/create_schema/user_schema.py

from sqlalchemy import CheckConstraint, Column, Integer, Text, UniqueConstraint, text

from app.core.db import Base
from app.models import DATETIME_RE

# sqlite 의 datetime('now') 대신 - 컬럼이 TEXT ISO-8601 이라 Postgres now() 를 같은 포맷 문자열로 캐스팅한다
NOW = text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint(
            "auth_provider IN ('google', 'firebase', 'kakao', 'apple', 'local')", name="ck_user_auth_provider"
        ),
        UniqueConstraint("auth_provider", "auth_uid", name="uq_user_auth"),
        CheckConstraint("length(trim(name)) > 0", name="ck_user_name"),
        # 엄밀한 이메일 검증이 아니다 - '@' 앞뒤와 도메인의 점만 본다
        CheckConstraint(r"email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'", name="ck_user_email"),
        CheckConstraint(f"created_at ~ {DATETIME_RE}", name="ck_user_created_at"),
        CheckConstraint(f"updated_at ~ {DATETIME_RE} AND updated_at >= created_at", name="ck_user_updated_at"),
        CheckConstraint(
            f"last_login_at ~ {DATETIME_RE} AND last_login_at >= created_at", name="ck_user_last_login_at"
        ),
        CheckConstraint(f"withdrawn_at ~ {DATETIME_RE} AND withdrawn_at >= created_at", name="ck_user_withdrawn_at"),
    )

    user_id = Column(Integer, primary_key=True)
    auth_provider = Column(Text, nullable=False, server_default=text("'local'"))
    auth_uid = Column(Text, nullable=False)
    email = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text)
    name = Column(Text, nullable=False)
    phone = Column(Text)
    region = Column(Text)
    last_login_at = Column(Text)
    withdrawn_at = Column(Text)
    created_at = Column(Text, nullable=False, server_default=NOW)
    updated_at = Column(Text, nullable=False, server_default=NOW)
