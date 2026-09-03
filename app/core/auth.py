# Last updated: 2026-09-03
# Last Updated : 2026-09-02

import jwt
import secrets
from fastapi import HTTPException, Header, status

from app.core.config import JWT_SECRET, JWT_ALGORITHM


def _decode_token(authorization: str, expected_role: str) -> dict:
    """Authorization: Bearer <jwt> 를 검증하고 payload를 돌려준다. role이 안 맞거나 실패하면 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 필요합니다.",
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

    if payload.get("role") != expected_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{expected_role} 권한이 없는 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_current_admin(authorization: str = Header(None)) -> int:
    """Authorization: Bearer <jwt> 를 검증하고 admin 역할인지 확인한다. 실패하면 401.
    관리자는 공용 비밀번호라 계정별 id가 없다 - 통과 여부만 의미 있다."""
    _decode_token(authorization, "admin")


def get_current_user(authorization: str = Header(None)) -> int:
    """Authorization: Bearer <jwt> 를 검증하고 user_id를 돌려준다. 실패하면 401."""
    payload = _decode_token(authorization, "user")
    return int(payload["sub"])
