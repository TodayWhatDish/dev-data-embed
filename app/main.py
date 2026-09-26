# Last updated: 2026-09-03
# Last Updated : 2026-09-03

"""API 서버의 진입점. uvicorn이 이 파일의 'app' 객체를 찾아 실행한다.

라우팅 규칙 자체(엔드포링트 함수)는 여기 두지 않고 routes/ 아래 파일로 나눈다.
main.py는 앱을 조립하고 라우터를 등록하는 역할만 한다.

*uvicorn은 실제로 TCP 포트를 열고, HTTP 요청을 받아 파싱하여 응답을 돌려보내는 ASGI서버이다.
FAST API 코드자체는 요청에 따른 함수 콜백만 정의할 뿐, 소켓을 열 능력이 없다.

"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import FRONTEND_ORIGINS
from app.core.db import request_scope
from app.core.exceptions import AppError

from app.api.routes.admin_auth import router as admin_auth_router
from app.api.routes.ask import router as ask_router
from app.api.routes.auth import router as auth_router
from app.api.routes.background import router as background_router
from app.api.routes.customers import router as customers_router
from app.api.routes.health import router as health_router
from app.api.routes.products import router as products_router
from app.api.routes.purchases import router as purchases_router
from app.api.routes.questions import router as questions_router
from app.app_logger.logger import init_logger

init_logger()
from app.api.lifespan import lifespan
from app.api.routes.recommend import router as recommend_router

from app.api.errors import app_error_handler



class SessionPerRequest:
    """요청마다 DB 세션을 따로 쓰고, 응답이 끝나면 닫는다 (app/core/db.py 의 request_scope).
    yield 의존성(get_db)이 아니라 미들웨어인 이유: 의존성의 정리 코드는 StreamingResponse(/ask)가
    끝나기 전에 돌아서, 스트리밍 중에 쓰는 세션을 못 닫는다."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async with request_scope():
            await self.app(scope, receive, send)


app = FastAPI(lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)
app.add_middleware(SessionPerRequest)

# dev-web(Next.js, 별도 저장소)이 다른 오리진에서 API를 부른다.
# 허용 오리진은 app.core.config.FRONTEND_ORIGINS(env FRONTEND_ORIGINS)에서 온다 -
# 배포 도메인은 코드가 아니라 배포 플랫폼의 환경변수로 넣는다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommend_router)
app.include_router(ask_router)
app.include_router(health_router)
app.include_router(admin_auth_router)
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(customers_router)
app.include_router(background_router)
app.include_router(purchases_router)
app.include_router(questions_router)
