# Last Updated : 2026-09-13
"""데이터베이스에 닿는 자리를 여기 하나로 모은다. SQLAlchemy 엔진/세션/Base 가 전부 여기 있다."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import SUPABASE_DB_URL


class Base(DeclarativeBase):
    """app/models/ 의 모든 ORM 모델이 여기서 상속한다."""


# postgresql:// 는 SQLAlchemy 기본값인 psycopg2 dialect 로 잡힌다 - 여기 깔린 건 psycopg(3) 라
# +psycopg 로 dialect 를 명시해야 한다.
_url = SUPABASE_DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# transaction pooler(포트 6543, Supavisor) 는 커넥션이 트랜잭션마다 다른 서버로 옮겨질 수 있어
# 서버사이드 prepared statement 를 못 쓴다 - psycopg 가 자동으로 준비하려는 걸 꺼야
# "prepared statement does not exist" 로 죽지 않는다.
# 요청 스레드(기본 40)는 요청 하나에 세션 1 + 벡터 검색 커넥션 1 을 쓴다. 풀이 다 차면
# pool_timeout(30초)까지 기다린다. pre_ping/recycle: 오래 놀던 커넥션을 pooler 가 끊어 놨으면
# 첫 요청이 죽지 않고 새로 연다.
# ponytail: 10+20 은 감으로 정한 값 - Supabase 플랜의 pooler 클라이언트 상한 안에서 부하 보고 조정.
engine = create_engine(
    _url,
    connect_args={"prepare_threshold": None},
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300,
)

# 세션은 요청마다 하나다. 라우트가 `db: Session = Depends(get_db)` 로 받아 service/repository 에
# 인자로 넘긴다 - 어느 함수가 DB 에 닿는지 시그니처에 드러난다.
# 요청 밖(lifespan/CLI/eval/테스트)은 `with new_session() as db:` 로 직접 열고 닫는다.
SessionLocal = sessionmaker(bind=engine)


def new_session() -> Session:
    """요청 밖용 세션. 부른 쪽이 닫는다 - `with new_session() as db:`"""
    return SessionLocal()


def get_db() -> Iterator[Session]:
    """FastAPI 의존성. 요청 하나당 세션 하나를 내어주고, 응답이 끝나면 닫는다.

    close() 는 커밋 안 된 트랜잭션을 롤백하고 연결을 풀에 돌려준다 - 요청이 끝나도
    트랜잭션이 열린 채(idle in transaction) 연결을 붙잡는 일이 없다.
    FastAPI 0.118 부터 yield 의존성의 정리 코드는 응답(StreamingResponse 포함)을 다 보낸 뒤에 돈다 -
    /ask 스트림 도중에 세션이 닫히지 않는다.
    """
    db = new_session()
    try:
        yield db
    finally:
        db.close()


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


def commit(db: Session, table: str | None = None) -> None:
    """세션을 커밋한다. 제약 위반(IntegrityError)만 QueryError 로 갈아끼운다.

    쓰기는 전부 이걸 통한다 — session.commit() 을 직접 부르면 이 변환을 건너뛴다.
    실패하면 롤백까지 한다. 안 하면 죽은 트랜잭션을 다음 쿼리가 그대로 물고 간다.

    주의: Query.update()/delete() 같은 벌크 연산은 flush 를 기다리지 않고 그 자리에서 바로
    UPDATE/DELETE 를 실행한다 - 그 IntegrityError 는 여기가 아니라 부른 쪽에서 잡아야 한다.
    """
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise as_query_error(e, table) from e


@contextmanager
def transaction(db: Session, table: str | None = None):
    """블록 안의 쓰기를 커밋 한 번으로 묶는다. 중간에 하나라도 실패하면 전부 롤백한다.
    블록 안의 repositories 는 commit() 대신 flush 만 한다 - 제약 위반은 flush 에서도 터지므로 여기서 같이 바꾼다.
    """
    try:
        yield
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise as_query_error(e, table) from e
    except Exception:
        db.rollback()
        raise


def _exec_driver_sql(db: Session, sql, params=()):
    """실제 SQL 실행 지점 - execute/fetch 전부 여기를 거치며, 실패하면 세션을 롤백해야 다음 쿼리가 산다.
    Postgress는 트랜잭션 안 문장 하나만 실패해도 롤백 전까진 그 커넥션 전체가 죽는다. 
    이걸 하지 않으면, 같은 세션의 다음 쿼리가 전부 PendingRollbackError 로 죽는다.
    """
    try:
        return db.connection().exec_driver_sql(sql, params)
    except Exception:
        db.rollback()
        raise

def execute(db: Session, sql, params=(), table: str | None = None) -> int:
    """ORM 모델이 없는 자리(관계 없는 자유 SQL DELETE 등)를 위한 쓰기 한 문장 + 커밋.
    영향받은 행 수를 돌려준다. 실패하면 _exec_driver_sql 이 롤백한다.
    """
    cur = _exec_driver_sql(db, sql, params)
    commit(db, table)
    return cur.rowcount


def fetch(db: Session, sql, params=()) -> list[dict]:
    """SELECT 결과를 행마다 dict 로 꺼낸다. 조인·집계처럼 ORM 모델 하나로 안 떨어지는 쿼리용.

    exec_driver_sql 은 SQLAlchemy 의 :name 바인딩을 거치지 않고 드라이버(sqlite3)의 ? 자리표시자를
    그대로 쓴다 — 기존 SQL 문자열을 하나도 안 고치고 세션을 통해서만 돌릴 수 있는 이유다.
    """
    cur = _exec_driver_sql(db, sql, params)
    return [dict(row) for row in cur.mappings()]


def fetch_one(db: Session, sql, params=()) -> dict | None:
    """SELECT 결과의 첫 행만 dict 로 꺼낸다. 없으면 None."""
    rows = fetch(db, sql, params)
    return rows[0] if rows else None


def fetch_tuples(db: Session, sql, params=()) -> list[tuple]:
    """SELECT 결과를 행마다 튜플로 꺼낸다. 컬럼 이름은 안 붙는다."""
    return _exec_driver_sql(db, sql, params).fetchall()


def fetch_tuple_one(db: Session, sql, params=()) -> tuple | None:
    """fetch_tuples 의 한 행짜리. 없으면 None."""
    return _exec_driver_sql(db, sql, params).fetchone()
