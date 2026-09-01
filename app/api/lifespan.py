# Last Updated : 2026-09-01

"""서버를 시작 시 DB와 모델을 사용할 수 있도록 미리 준비한다."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from pipeline.vector_db import connect

@asynccontextmanager
async def lifespan(app: FastAPI):
    """uvicorn이 요청을 받기 전/후에 앱에게 보내는 ASGI lifespan 이벤트를 처리."""
    app.state.con = connect()
    yield
    app.state.con.close()