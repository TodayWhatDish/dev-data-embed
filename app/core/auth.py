# Last Updated : 2026-09-01

import hashlib
import secrets

import jwt
from fastapi import HTTPException,Header,status

from app.core.config import JWT_SECRET,JWT_ALGORITHM

PBKDF2_ITERATIONS = 200_000

def hash_password(password: str, salt: bytes = None) -> tuple[bytes, bytes]:
    """비밀번호를 해시하고 salt를 반환한다. salt가 주어지면 그걸 쓰고, 없으면 새로 만든다."""
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITERATIONS)
    return f"{salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    """비밀번호를 검증한다. salt와 해시값이 주어져야 한다."""
    salt, digest = password_hash.split('$',1)
    new_digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITERATIONS).hex()
    return secrets.compare_digest(digest, new_digest)

def get_current_admin(authorization: str = Header(None)) -> int:
    """Authorization: Bearer <jwt> 를 검증하고 admin_id를 돌려준다. 실패하면 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "관리자 토큰이 필요합니다.",
            headers = {"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 권한이 없는 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload["admin_id"]