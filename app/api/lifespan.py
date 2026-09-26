# Last Updated : 2026-09-03

"""서버를 시작 시 DB와 모델을 사용할 수 있도록 미리 준비한다.

main.py 는 앱을 조립하고 라우터를 등록하는 일만 한다(그 파일 독스트링). 기동 시 1회 적재는
전부 여기로 모은다 — uvicorn 이 요청을 받기 전에 도는 자리가 여기뿐이라서다.

담는 것은 두 가지고, 서로 성격이 다르다:
  * 도메인 마스터 : DB 값을 도메인 싱글턴에 얹는다 (알러지/축종/품종/카테고리...)
  * 스키마 확인   : ORM Base.metadata 에 매핑된 테이블이 실제 DB 에도 있는지 기동 때 미리 본다
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect

from app.core.config import ADMIN_PASSWORD, JWT_SECRET
from app.core.db import get_engine, new_session
from app.domain.domain_init import init_from_db

logger = logging.getLogger()


def load_domain_cache():
    """도메인 마스터 테이블을 싱글턴에 얹는다.

    이게 없으면 CommonMgr 이 빈 채로 남아 services.profile.resolve_allergy() 가
    첫 요청에서 AttributeError 로 죽는다. 지금까지 fake_main.py 만 이걸 불렀다.
    """
    with new_session() as db:  # 적재가 끝나면 닫아 연결을 풀에 돌려준다
        init_from_db(db)


def load_schema_cache():
    """DB 에 실재하는 테이블 이름을 읽어서 몇 개인지 남긴다.

    ORM 모델은 컬럼 이름을 코드에 고정해 두므로 general_query 시절의 런타임 화이트리스트는
    더 이상 필요 없다. 그래도 여기서 한 번 접속해 보는 이유는 남아 있다 — DB 가 비었거나
    파일이 없으면 첫 요청이 아니라 기동에서 티가 난다.
    """
    tables = inspect(get_engine()).get_table_names()
    logger.info(f"Cached schema: table={len(tables)}")
    return tables


def check_secrets():
    """비밀값이 비면 빈 비밀번호 로그인,토큰 위조가 가능해지기에 기동을 막는다."""
    if not ADMIN_PASSWORD:
        raise RuntimeError("ADMIN_PASSWORD 환경변수가 비어 있습니다.")
    if len(JWT_SECRET) < 32: # 32 Byte
        raise RuntimeError("JWT_SECRET 은 32자 이상이어야합니다.") 


@asynccontextmanager
async def lifespan(app: FastAPI):
    """uvicorn이 요청을 받기 전/후에 앱에게 보내는 ASGI lifespan 이벤트를 처리."""
    try:
        check_secrets()
        load_domain_cache()
        load_schema_cache()
    except Exception:
        # 실패 사유와 트레이스백은 아래 층(repositories)이 이미 찍었다. 여기서 남기는 건
        # '그래서 서버가 안 떴다' 는 사실이다 - 예외를 삼키지 않아 uvicorn 이 기동을 멈춘다.
        # 캐시가 빈 채로 요청을 받으면 첫 호출에서야 죽는데, 그때는 원인이 훨씬 멀어져 있다
        logger.critical("기동 실패 - 캐시를 못 채웠습니다. 서버를 띄우지 않습니다")
        raise

    logger.info("Lifespan startup done")
    yield

    get_engine().dispose()
    logger.info("Lifespan shutdown done")
