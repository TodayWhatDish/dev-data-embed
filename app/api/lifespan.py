# Last Updated : 2026-09-03

"""서버를 시작 시 DB와 모델을 사용할 수 있도록 미리 준비한다.

main.py 는 앱을 조립하고 라우터를 등록하는 일만 한다(그 파일 독스트링). 기동 시 1회 적재는
전부 여기로 모은다 — uvicorn 이 요청을 받기 전에 도는 자리가 여기뿐이라서다.

담는 것은 네 가지고, 서로 성격이 다르다:
  * 비밀값 검사   : ADMIN_PASSWORD/JWT_SECRET 이 비었거나 짧으면 기동 자체를 막는다
  * 도메인 마스터 : DB 값을 도메인 싱글턴에 얹는다 (알러지/축종/품종/카테고리...)
  * 스키마 확인   : ORM Base.metadata 에 매핑된 테이블이 실제 DB 에도 있는지 기동 때 미리 본다
  * 벡터 커넥션   : pipeline/vector_db.py 가 여는 별도 SQLAlchemy 커넥션. engine 과 다른 물건이다
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect

from app.core.config import ADMIN_PASSWORD, JWT_SECRET
from app.core.db import engine
from app.domain.domain_init import init_from_db
from pipeline.vector_db import connect

logger = logging.getLogger()


def load_domain_cache():
    """도메인 마스터 테이블을 싱글턴에 얹는다.

    이게 없으면 CommonMgr 이 빈 채로 남아 services.profile.resolve_allergy() 가
    첫 요청에서 AttributeError 로 죽는다. 지금까지 fake_main.py 만 이걸 불렀다.
    """
    init_from_db()


def load_schema_cache():
    """DB 에 실재하는 테이블 이름을 읽어서 몇 개인지 남긴다.

    ORM 모델은 컬럼 이름을 코드에 고정해 두므로 general_query 시절의 런타임 화이트리스트는
    더 이상 필요 없다. 그래도 여기서 한 번 접속해 보는 이유는 남아 있다 — DB 가 비었거나
    파일이 없으면 첫 요청이 아니라 기동에서 티가 난다.
    """
    tables = inspect(engine).get_table_names()
    logger.info(f"Cached schema: table={len(tables)}")
    return tables


def check_secrets():
    """비밀값이 비면 빈 비밀번호 로그인·토큰 위조가 가능해지므로 기동을 막는다."""
    if not ADMIN_PASSWORD:
        raise RuntimeError("ADMIN_PASSWORD 환경변수가 비어 있습니다.")
    if len(JWT_SECRET) < 32:  # HS256 권장 최소 키 길이(256bit)
        raise RuntimeError("JWT_SECRET 은 32자 이상이어야 합니다.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """uvicorn이 요청을 받기 전/후에 앱에게 보내는 ASGI lifespan 이벤트를 처리."""
    try:
        check_secrets()
        load_domain_cache()
        load_schema_cache()
        app.state.con = connect()
    except Exception:
        # 원인은 위 예외 메시지가 말한다. 여기서는 '서버가 안 떴다'는 사실만 남기고 다시 던진다 -
        # 삼키면 설정·캐시가 빈 채로 요청을 받아, 첫 호출에서야 원인에서 먼 곳이 죽는다.
        logger.critical("기동 실패 - 서버를 띄우지 않습니다")
        raise

    logger.info("Lifespan startup done")
    yield

    app.state.con.close()
    logger.info("Lifespan shutdown done")
