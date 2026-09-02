# Last Updated : 2026-09-02

"""관리자 로그인 검증 + JWT 토큰 발급"""

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from app.core.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES, ADMIN_PASSWORD


def login(password: str) -> str:
    """공용 비밀번호를 검증하고, 맞으면 JWT 토큰을 발급한다. 틀리면 ValueError."""
    if not secrets.compare_digest(password, ADMIN_PASSWORD):
        raise ValueError("비밀번호가 틀립니다.")

    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    token = jwt.encode(
        {"role": "admin", "exp": expire},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return token
