# Last Updated: 2026-08-17
"""
계정 — 서비스 가입자(보호자).

하위 테이블이 참조하는 소유자 키는 오직 user.user_id 다.
외부 인증 ID(auth_uid)를 FK 로 쓰지 않는 이유는 docu/schema/user_schema.md#user 참고.

의존: 없음.

설계 규칙 전문은 execute_schema.py, 컬럼 설명은 docu/schema/user_schema.md.
"""

TABLES = [

# user — 보호자 계정. 컬럼 설명은 docu/schema/user_schema.md#user
'''
CREATE TABLE user (
    user_id       INTEGER NOT NULL PRIMARY KEY,
    auth_provider TEXT    NOT NULL DEFAULT 'local'
                          CHECK (auth_provider IN ('google', 'firebase', 'kakao', 'apple', 'local')),
    auth_uid      TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    phone         TEXT,
    region        TEXT,
    last_login_at TEXT    CHECK (last_login_at IS NULL OR datetime(last_login_at) IS NOT NULL),
    withdrawn_at  TEXT    CHECK (withdrawn_at IS NULL OR datetime(withdrawn_at) IS NOT NULL),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
) STRICT
''',

]


# 같은 외부 계정이 두 유저에 붙는 것을 DB 레벨에서 차단한다.
# 로그인 처리는 이 인덱스를 그대로 타는 조회 하나로 끝난다:
#   SELECT user_id FROM user WHERE auth_provider = ? AND auth_uid = ?
UNIQUE_INDEXES = [
    'CREATE UNIQUE INDEX uq_user_auth      ON user(auth_provider, auth_uid)',
]
