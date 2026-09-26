# Last Updated : 2026-09-25

"""비밀번호 해싱/검증 + JWT 발급. 토큰을 만드는 곳은 여기 하나뿐이다(검증은 api/deps.py)."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET


def hash_password(password: str) -> str:
    """bcrypt 해시. 72바이트 초과는 ValueError라 호출 전에 길이를 막는다."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """저장된 해시와 비교한다. bcrypt.checkpw가 타이밍 공격을 막아준다."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(role: str, sub: str | None = None) -> str:
    """role(+sub)을 담아 JWT를 발급한다. 관리자는 계정별 id가 없어서 sub가 없다."""
    payload = {"role": role, "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)}
    if sub is not None:
        payload["sub"] = sub
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _demo() -> None:
    """해싱 -> 검증 왕복과, 틀린 비밀번호 거부를 확인한다."""
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)
    print("security 자체 점검 통과")


if __name__ == "__main__":
    _demo()
