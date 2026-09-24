# Last Updated : 2026-09-02

"""관리자 로그인 검증 + JWT 토큰 발급"""

import secrets

from app.core.config import ADMIN_PASSWORD
from app.core.exceptions import Unauthorized
from app.core.security import create_access_token


def login(password: str) -> str:
    """공용 비밀번호를 검증하고, 맞으면 JWT 토큰을 발급한다. 틀리면 Unauthorized."""
    if not secrets.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
        raise Unauthorized("비밀번호가 틀립니다.")

    return create_access_token("admin")
