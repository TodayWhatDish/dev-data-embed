# Last Updated : 2026-08-30

"""API 서버의 진입점. uvicorn이 이 파일의 'app' 객체를 찾아 실행한다.

    라우팅 규칙 자체(엔드포인트 함수)는 여기 두지 않고 routes/ 아래 파일로 나눈다.
    main.py는 앱을 조립하고 라우터를 등록하는 역할만 한다.

    *uvicorn은 실제로 TCP 포트를 열고, HTTP 요청을 받아 파싱하여 응답을 돌려보내는 ASGI서버이다.
    FAST API 코드자체는 요청에 따른 함수 콜백만 정의할 뿐, 소켓을 열 능력이 없다.

"""
import sqlite3
from contextlib import asynccontextmanager

import sqlite_vec
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, recommend
from app.core.config import DB_PATH
from app.core.embedder import get_embeddings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """uvicorn이 요청을 받기 전/후에 앱에게 보내는 ASGI lifespan 이벤트를 처리, yield 앞은 시작 시, 뒤는 종료 시 1회씩 실행

    임베딩 모델 로딩과 벡터 읽기를 여기서 한 번만 치른다. 요청마다 하면 첫 응답까지
    수 초씩 걸리고, 같은 모델이 여러 벌 메모리에 올라간다.

    check_same_thread=False 인 이유 ─ FastAPI 는 def(동기) 엔드포인트를 스레드풀에서
    돌린다. 기본값이면 커넥션을 만든 스레드가 아닌 곳에서 쓴다고 sqlite3 가 막는다.
    """
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    # vec_distance_cosine 은 SQLite 기본 함수가 아니라 sqlite_vec 이 심어주는 확장이다.
    # 여기서 안 올리면 검색 쿼리가 'no such function' 으로 죽는다.
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    app.state.con = con

    # 모델은 싱글톤이라 첫 호출에서만 로드된다. 그 첫 호출을 여기서 미리 치러
    # 첫 요청이 수십 초를 떠안지 않게 한다 (위 docstring 이 약속한 동작).
    get_embeddings()
    yield
    con.close()


app = FastAPI(title="pet-reco", lifespan=lifespan)

# 브라우저에서 직접 부를 수 있게 열어둔다. 배포 시에는 도메인을 좁혀야 한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(recommend.router)
