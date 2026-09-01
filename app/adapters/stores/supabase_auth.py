"""슈퍼베이스 세션 토큰을 검증하는 자리. 반환 모양은 google_auth.py와 동일하게 맞춘다."""

from supabase import create_client

from app.core.config import SUPABASE_KEY, SUPABASE_URL

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def verify_supabase_token(access_token: str) -> dict:
    """실패하면 예외(Exception)를 던진다."""
    result = supabase.auth.get_user(access_token)
    user = result.user
    return {
        "sub": user.id,
        "email": user.email,
        "name": (user.user_metadata or {}).get("name", ""),
    }