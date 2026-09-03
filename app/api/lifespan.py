# Last Updated : 2026-09-03

"""서버를 시작 시 DB와 모델을 사용할 수 있도록 미리 준비한다.

main.py 는 앱을 조립하고 라우터를 등록하는 일만 한다(그 파일 독스트링). 기동 시 1회 적재는
전부 여기로 모은다 — uvicorn 이 요청을 받기 전에 도는 자리가 여기뿐이라서다.

담는 것은 세 가지고, 서로 성격이 다르다:
  * 도메인 마스터 : DB 값을 도메인 싱글턴에 얹는다 (알러지/축종/품종/카테고리...)
  * 스키마 정보   : general_query 가 컬럼 이름을 거를 때 쓰는 화이트리스트
  * 벡터 커넥션   : sqlite_vec 확장이 얹힌 별도 커넥션. 전역 con 과 다른 물건이다
"""

import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.domain.domain_init import init_from_db
from app.repositories.general_query import ColumnMgr, get_all_table_names
from pipeline.vector_db import connect

logger = logging.getLogger()


def load_domain_cache():
    """도메인 마스터 테이블을 싱글턴에 얹는다.

    이게 없으면 CommonMgr 이 빈 채로 남아 features.profile.resolve_allergy() 가
    첫 요청에서 AttributeError 로 죽는다. 지금까지 fake_main.py 만 이걸 불렀다.
    """
    init_from_db()

def load_schema_cache():
    """테이블·컬럼 이름을 ColumnMgr 에 담고 몇 개를 담았는지 남긴다.

    ColumnMgr 은 첫 호출 때 스스로 채우니 안 불러도 돌아가긴 한다. 그래도 여기서 깨우는 이유는
    두 가지다 — 21개 테이블을 읽는 값을 첫 요청이 물지 않고, DB 가 비었거나 스키마가 어긋나면
    기동에서 티가 난다. 첫 쓰기 요청에서 unknown_table 로 알게 되는 것보다 낫다.
    """
    col_mgr = ColumnMgr.get_inst()
    tables = get_all_table_names()
    logger.info(f'Cached schema: table={len(tables)}, '
                f'column={sum(len(col_mgr.get_col_names(t)) for t in tables)}')
    return tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    """uvicorn이 요청을 받기 전/후에 앱에게 보내는 ASGI lifespan 이벤트를 처리."""
    try:
        load_domain_cache()
        load_schema_cache()
        app.state.con = connect()
    except Exception:
        # 실패 사유와 트레이스백은 아래 층(repositories)이 이미 찍었다. 여기서 남기는 건
        # '그래서 서버가 안 떴다' 는 사실이다 - 예외를 삼키지 않아 uvicorn 이 기동을 멈춘다.
        # 캐시가 빈 채로 요청을 받으면 첫 호출에서야 죽는데, 그때는 원인이 훨씬 멀어져 있다
        logger.critical('기동 실패 - 캐시를 못 채웠습니다. 서버를 띄우지 않습니다')
        raise

    logger.info('Lifespan startup done')
    yield

    app.state.con.close()
    logger.info('Lifespan shutdown done')
