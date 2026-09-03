# Last Updated : 2026-09-03

"""비밀번호 해싱/검증. stdlib(hashlib, secrets)만 쓴다 — 새 의존성 없음."""
import hashlib
import secrets

_ITERATIONS = 200_000  # OWASP 권장 PBKDF2-HMAC-SHA256 최소치


def hash_password(password: str) -> str:
    """salt$hash 형식 문자열 하나로 저장한다. 컬럼 하나로 충분하다."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """저장된 salt로 같은 연산을 재현해 compare_digest로 비교한다(타이밍 공격 방지)."""
    salt, _, hexdigest = password_hash.partition("$")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return secrets.compare_digest(digest.hex(), hexdigest)


def _demo() -> None:
    """해싱 → 검증 왕복과, 틀린 비밀번호 거부를 확인한다."""
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)
    print("security 자체 점검 통과")


if __name__ == "__main__":
    _demo()
