# Last Updated : 2026-09-02

import jwt
from fastapi import HTTPException, Header, status

from app.core.config import JWT_SECRET, JWT_ALGORITHM


def get_current_admin(authorization: str = Header(None)) -> int:
    """Authorization: Bearer <jwt> 를 검증하고 admin_id를 돌려준다. 실패하면 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 토큰이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
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
