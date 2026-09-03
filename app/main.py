# Last updated: 2026-09-03
# Last Updated : 2026-09-01

"""API 서버의 진입점. uvicorn이 이 파일의 'app' 객체를 찾아 실행한다.

    라우팅 규칙 자체(엔드포링트 함수)는 여기 두지 않고 routes/ 아래 파일로 나눈다.
    main.py는 앱을 조립하고 라우터를 등록하는 역할만 한다.

    *uvicorn은 실제로 TCP 포트를 열고, HTTP 요청을 받아 파싱하여 응답을 돌려보내는 ASGI서버이다.
    FAST API 코드자체는 요청에 따른 함수 콜백만 정의할 뿐, 소켓을 열 능력이 없다.

"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.ask import router as ask_router
from app.api.routes.health import router as health_router
from app.api.routes.admin_auth import router as admin_auth_router
from app.api.routes.products import router as products_router
from app.api.routes.customers import router as customers_router
from app.app_logger.logger import init_logger
from app.core.config import ROOT

init_logger()
from app.api.routes.recommend import router as recommend_router
from app.api.lifespan import lifespan

app = FastAPI(lifespan=lifespan)

# dev-web(Next.js, 별도 저장소)이 다른 오리진에서 API를 부른다 - 배포 도메인 정해지면 추가.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommend_router)
app.include_router(ask_router)
app.include_router(health_router)
app.include_router(admin_auth_router)
app.include_router(products_router)
app.include_router(customers_router)
# web/ 정적 마운트는 admin.html/js를 dev-web/frontend/public/admin/로 옮기며 제거했다.
# 프론트는 이제 dev-web(별도 저장소, http://localhost:3000)에서 띄운다.

@app.get("/health")
def health():
    """서버가 살아있는지 확인하는 Health Check. 배포 환경에서 로드밸런서(load balancer)가 주기적으로 호출"""
    return{"status":"ok"}