# Last Updated : 2026-09-01

"""로그인 시 입력한 username이 실제 admin 테이블에 있는지 조회"""

from app.core.db import one

def find_by_username(username: str) -> dict | None:
    """username으로 admin 행 하나를 조회한다. (admin_id, password_hash) 없으면 None."""
    sql = "SELECT admin_id, password_hash FROM admin WHERE username = ?"
    return one(sql, (username,))