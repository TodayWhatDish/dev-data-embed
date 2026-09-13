# 계정 ORM 모델. 스키마 정의는 pipeline/create_schema/user_schema.py

from sqlalchemy import Column, Integer, Text, text

from app.core.db import Base

NOW = text("(datetime('now'))")


class User(Base):
    __tablename__ = "user"

    user_id = Column(Integer, primary_key=True)
    auth_provider = Column(Text, nullable=False, server_default=text("'local'"))
    auth_uid = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    password_hash = Column(Text)
    name = Column(Text, nullable=False)
    phone = Column(Text)
    region = Column(Text)
    last_login_at = Column(Text)
    withdrawn_at = Column(Text)
    created_at = Column(Text, nullable=False, server_default=NOW)
    updated_at = Column(Text, nullable=False, server_default=NOW)
