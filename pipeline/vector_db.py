# 검색/색인 양쪽이 쓰는 DB 커넥션 진입점. 예전엔 sqlite-vec 확장을 얹은 sqlite3 커넥션이었는데,
# DB가 Supabase(Postgres)로 이관되면서 SQLAlchemy Connection으로 바뀌었다 - 이 함수 하나만
# 바뀌면 되게, 부르는 쪽(query.py/eval/*)은 그대로 둔다.
# API 는 이걸 안 쓴다 - 요청 세션의 db.connection() 으로 검색한다(services/searching.py).

from app.core.db import get_engine


def connect():
    """
    # Summary
    * 요청/스크립트 하나가 쓸 DB 커넥션을 연다
    # info
    * CLI/eval의 with 블록이 닫는다
    # examples
    * 인자 없음 -> get_engine().connect()
    * -> SQLAlchemy Connection (닫는 건 부르는 쪽)
    """
    return get_engine().connect()
