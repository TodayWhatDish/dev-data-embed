# Last Updated : 2026-09-01

"""user 테이블에 연결되는 곳. 현재는 구글 로그인 조회/갱신/가입만 다룬다."""

def find_by_google_uid(sub: str) -> int | None:
    raise NotImplementedError

def touch_login(user_id: int) -> None:
    raise NotImplementedError

def create_google_user(sub: str, email: str, name: str) -> int:
    raise NotImplementedError