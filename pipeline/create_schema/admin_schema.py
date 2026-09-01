# Last Updated : 2026-09-01

"""관리자 계정 - 로그인용. user(보호자)와는 성격이 달라 별로 테이블로 구성"""

TABLES = [

# admin — 로그인 계정. password_hash 는 평문이 아니라 해시 문자열 하나만 저장한다.
'''
CREATE TABLE admin (
    admin_id      INTEGER NOT NULL PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
) STRICT
''',

]