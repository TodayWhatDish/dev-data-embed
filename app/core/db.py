# Last Updated : 2026-09-13
"""데이터베이스에 닿는 자리를 여기 하나로 모은다. SQLAlchemy 엔진/세션/Base 가 전부 여기 있다."""

import threading

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, scoped_session, sessionmaker

from app.core.config import SUPABASE_DB_URL


class Base(DeclarativeBase):
    """app/models/ 의 모든 ORM 모델이 여기서 상속한다."""


# postgresql:// 는 SQLAlchemy 기본값인 psycopg2 dialect 로 잡힌다 - 여기 깔린 건 psycopg(3) 라
# +psycopg 로 dialect 를 명시해야 한다.
_url = SUPABASE_DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# transaction pooler(포트 6543, Supavisor) 는 커넥션이 트랜잭션마다 다른 서버로 옮겨질 수 있어
# 서버사이드 prepared statement 를 못 쓴다 - psycopg 가 자동으로 준비하려는 걸 꺼야
# "prepared statement does not exist" 로 죽지 않는다.
engine = create_engine(_url, connect_args={"prepare_threshold": None})

# 스레드마다 자기 세션을 쓴다. 전에는 모듈 전역 커넥션 하나를 check_same_thread=False 로 열어
# 다 같이 썼는데, 라우트가 전부 def(= async 아님)라 FastAPI 가 스레드풀에서 돌린다.
# 같은 세션(=커넥션 하나를 물고 있다)을 여러 스레드가 동시에 쓰면 sqlite3 커넥션 내부 상태가
# 깨져서 InterfaceError('bad parameter or other API misuse') 가 난다
# (4스레드 동시 SELECT 12,000회 중 1,121회 실패 — 실측은 docs/WORK.md 2026-09-03 §5).
# 스레드당 하나면 그 공유 자체가 없어진다. 세션은 닫지 않는다 — 스레드풀 스레드는 프로세스가
# 살아있는 동안 재사용되므로 스레드 수(기본 40)만큼만 열리고, 그게 상한이다.
SessionLocal = scoped_session(sessionmaker(bind=engine), scopefunc=threading.get_ident)


def get_session() -> Session:
    """이 스레드 전용 세션. DB 에 닿는 모든 함수가 여기를 거친다."""
    return SessionLocal()


def as_dict(row) -> dict:
    """ORM 모델 인스턴스 하나를 repositories 계약(list[dict]/dict)대로 편다."""
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


class QueryError(Exception):
    """
    # Summary
    * 쿼리가 거절된 이유를 담아 위층으로 올린다

    # info
    * reason 으로 책임 소재가 갈린다 — 위층이 이걸 보고 HTTP 상태를 정한다
        * constraint_* : DB 가 거절한 것. 들어온 값이 잘못됐다 -> 400/409
        * 그 밖(unknown_column, no_values ...) : 우리가 SQL 을 안 만든 것.
          부른 쪽 코드가 잘못 쓴 거라 서버 버그다 -> 500
    * 사유를 문자열 하나로 뭉개지 않는 이유는, 위층이 문자열을 파싱하게 만들면 안 되기 때문이다

    # params
    * reason: 위 목록 중 하나
    * table: 어느 테이블에서 났는지. 모르면 None
    * detail: 어떤 컬럼이 틀렸는지 등 사람이 볼 부연
    """

    def __init__(self, reason, table=None, detail=None):
        super().__init__(f"{reason}: table={table}, detail={detail}")
        self.reason = reason
        self.table = table
        self.detail = detail


# postgres 제약 위반 SQLSTATE -> reason. 메시지 문자열을 파싱하지 않으려고 SQLSTATE 코드를 쓴다
# (psycopg 예외는 클래스/인스턴스 양쪽에 .sqlstate 를 들고 있다)
CONSTRAINT_REASON = {
    "23505": "constraint_unique",  # unique_violation (PK 충돌 포함)
    "23514": "constraint_check",  # check_violation
    "23503": "constraint_fk",  # foreign_key_violation
    "23502": "constraint_notnull",  # not_null_violation
}


def as_query_error(e: IntegrityError, table: str | None) -> QueryError:
    """IntegrityError.orig 가 원래 psycopg 예외다 - sqlstate 는 거기 있다."""
    orig = e.orig
    return QueryError(
        CONSTRAINT_REASON.get(getattr(orig, "sqlstate", ""), "constraint_other"), table, str(orig)
    )


def commit(table: str | None = None) -> None:
    """이 스레드 세션을 커밋한다. 제약 위반(IntegrityError)만 QueryError 로 갈아끼운다.

    쓰기는 전부 이걸 통한다 — session.commit() 을 직접 부르면 이 변환을 건너뛴다.
    실패하면 롤백까지 한다. 안 하면 죽은 트랜잭션을 다음 쿼리가 그대로 물고 간다.

    주의: Query.update()/delete() 같은 벌크 연산은 flush 를 기다리지 않고 그 자리에서 바로
    UPDATE/DELETE 를 실행한다 - 그 IntegrityError 는 여기가 아니라 부른 쪽에서 잡아야 한다.
    """
    session = get_session()
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        raise as_query_error(e, table) from e


def execute(sql, params=(), table: str | None = None) -> int | None:
    """ORM 모델이 없는 자리(관계 없는 자유 SQL DELETE 등)를 위한 쓰기 한 문장 + 커밋.
    lastrowid 를 돌려준다 - INSERT 가 아니면 의미는 없지만 무해하다.
    """
    cur = get_session().connection().exec_driver_sql(sql, params)
    commit(table)
    try:
        return cur.lastrowid
    except AttributeError:
        # postgres 드라이버는 INSERT 가 아니면 lastrowid 자체가 없다(sqlite3 는 None) - 여기 호출부는
        # 전부 DELETE 라 어차피 안 쓰는 값이다
        return None


def fetch(sql, params=()) -> list[dict]:
    """SELECT 결과를 행마다 dict 로 꺼낸다. 조인·집계처럼 ORM 모델 하나로 안 떨어지는 쿼리용.

    exec_driver_sql 은 SQLAlchemy 의 :name 바인딩을 거치지 않고 드라이버(sqlite3)의 ? 자리표시자를
    그대로 쓴다 — 기존 SQL 문자열을 하나도 안 고치고 세션을 통해서만 돌릴 수 있는 이유다.
    """
    cur = get_session().connection().exec_driver_sql(sql, params)
    return [dict(row) for row in cur.mappings()]


def fetch_one(sql, params=()) -> dict | None:
    """SELECT 결과의 첫 행만 dict 로 꺼낸다. 없으면 None."""
    rows = fetch(sql, params)
    return rows[0] if rows else None


def fetch_tuples(sql, params=()) -> list[tuple]:
    """SELECT 결과를 행마다 튜플로 꺼낸다. 컬럼 이름은 안 붙는다."""
    return get_session().connection().exec_driver_sql(sql, params).fetchall()


def fetch_tuple_one(sql, params=()) -> tuple | None:
    """fetch_tuples 의 한 행짜리. 없으면 None."""
    return get_session().connection().exec_driver_sql(sql, params).fetchone()
