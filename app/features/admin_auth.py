# Last Updated : 2026-09-01

"""관리자 로그인 검증 + JWT 토큰 발급"""

from datetime import datetime, timedelta,timezone

import jwt
from app.core.config import JWT_SECRET,JWT_ALGORITHM,JWT_EXPIRE_MINUTES
from app.core.auth import verify_password
from app.repositories.admin import find_by_username

def login(username: str, password: str) -> str:
    """username과 password를 검증하고, 맞으면 JWT 토큰을 발급한다. 틀리면 None."""
    admin = find_by_username(username)
    if admin is None:
        raise ValueError("관리자 계정이 존재하지 않습니다.")

    admin_id, password_hash = admin
    if not verify_password(password, password_hash):
        raise ValueError("비밀번호가 틀립니다.")

    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    token = jwt.encode(
        {"admin_id": admin_id,
         "role": "admin",
         "exp": expire}, 
         JWT_SECRET, 
         algorithm=JWT_ALGORITHM,
    )
    return token
    