# 계정 ORM 모델. 스키마 정의는 pipeline/create_schema/user_schema.py

from sqlalchemy import CheckConstraint, Column, Integer, Text, UniqueConstraint, text

from app.core.db import Base

# sqlite 의 datetime('now') 대신 - 컬럼이 TEXT ISO-8601 이라 Postgres now() 를 같은 포맷 문자열로 캐스팅한다
NOW = text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint(
            "auth_provider IN ('google', 'firebase', 'kakao', 'apple', 'local')", name="ck_user_auth_provider"
        ),
        UniqueConstraint("auth_provider", "auth_uid", name="uq_user_auth"),
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
