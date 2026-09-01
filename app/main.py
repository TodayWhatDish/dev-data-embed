# Last Updated : 2026-08-27

"""API 서버의 진입점. uvicorn이 이 파일의 'app' 객체를 찾아 실행한다.

    라우팅 규칙 자체(엔드포링트 함수)는 여기 두지 않고 routes/ 아래 파일로 나눈다.
    main.py는 앱을 조립하고 라우터를 등록하는 역할만 한다.

    *uvicorn은 실제로 TCP 포트를 열고, HTTP 요청을 받아 파싱하여 응답을 돌려보내는 ASGI서버이다.
    FAST API 코드자체는 요청에 따른 함수 콜백만 정의할 뿐, 소켓을 열 능력이 없다.

"""
import sqlite3
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.app_logger.logger import init_logger

init_logger()
from app.api.routers.recommend import router as recommend_router
from app.api.routers.auth import router as auth_router

from pipeline.vector_db import connect


@asynccontextmanager
async def lifespan(app: FastAPI):
    """uvicorn이 요청을 받기 전/후에 앱에게 보내는 ASGI lifespan 이벤트를 처리, yield 앞은 시작 시, 뒤는 종료 시 1회씩 실행"""
    app.state.con = connect()
    yield
    app.state.con.close()


app = FastAPI(lifespan=lifespan)
app.include_router(recommend_router)
app.include_router(auth_router)

@app.get("/health")
def health():
    """서버가 살아있는지 확인하는 Health Check. 배포 환경에서 로드밸런서(load balancer)가 주기적으로 호출"""
    return{"status":"ok"}