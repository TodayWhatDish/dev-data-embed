# Last Updated : 2026-09-01

"""user 테이블에 연결되는 곳. 현재는 구글 로그인 조회/갱신/가입만 다룬다."""
from app.core.db import one, query, con

def find_by_google_uid(sub: str) -> int | None:
    """auth_provider = 'google'인 user_id를 반환한다. 없으면 None."""
    row = one("SELECT user_id FROM user WHERE auth_provider = 'google' AND auth_provider_uid = ?", (sub,))
    return row[0] if row else None

def touch_login(user_id: int) -> None:
    """last_login_at를 현재 시각으로 갱신한다."""
    query("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    con.commit()  # UPDATE는 commit을 해줘야 실제 DB에 반영된다.

def create_google_user(sub: str, email: str, name: str) -> int:
    """user 행을 만들고 새 user_id를 돌려준다."""
    query("INSERT INTO users (auth_provider, auth_provider_uid, email, name) VALUES (?, ?, ?, ?)", ("google", sub, email, name))
    con.commit()
    return find_by_google_uid(sub)