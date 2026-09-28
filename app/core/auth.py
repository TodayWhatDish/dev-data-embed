# Last updated: 2026-09-03
# Last Updated : 2026-09-02


import jwt
from fastapi import Header, HTTPException, status

from app.core.config import JWT_ALGORITHM, JWT_SECRET


def _decode_token(authorization: str, expected_role: str) -> dict:
    """Authorization: Bearer <jwt> 를 검증하고 payload를 돌려준다.

    토큰이 없거나 깨졌으면 401(다시 로그인), 유효한데 role만 다르면 403(로그인은 맞고 권한이 없다).
    화면은 401에서만 로그아웃시킨다 - 403까지 401로 주면 권한 없는 버튼 하나에 세션이 끊긴다.
    """
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
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{expected_role} 권한이 없는 토큰입니다.",
        )
    return payload


def get_current_admin(authorization: str = Header(None)) -> None:
    """Authorization: Bearer <jwt> 를 검증하고 admin 역할인지 확인한다. 실패하면 401, 역할이 다르면 403.
    관리자는 공용 비밀번호라 계정별 id가 없다 - 통과 여부만 의미 있다."""
    _decode_token(authorization, "admin")


def get_current_user(authorization: str = Header(None)) -> int:
    """Authorization: Bearer <jwt> 를 검증하고 user_id를 돌려준다. 실패하면 401, 역할이 다르면 403."""
    payload = _decode_token(authorization, "user")
    return int(payload["sub"])
