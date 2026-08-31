"""구글 로그인 payload를 받아 user 테이블과 맞춰보는 자리. 있으면 로그인, 없으면 가입."""

from app.core.db import query, one, con


def login_or_signup(google_payload: dict) -> int:
    sub = google_payload["sub"]
    row = one("SELECT user_id FROM user WHERE auth_provider = 'google' AND auth_uid = ?", (sub,))

    if row:
        user_id = row[0]
        query("UPDATE user SET last_login_at = datetime('now') WHERE user_id = ?", (user_id,))
        con.commit()
        return user_id

    query("""
        INSERT INTO user (auth_provider, auth_uid, email, name, last_login_at)
        VALUES ('google', ?, ?, ?, datetime('now'))
    """, (sub, google_payload["email"], google_payload["name"]))
    con.commit()

    return one("SELECT user_id FROM user WHERE auth_provider = 'google' AND auth_uid = ?", (sub,))[0]
