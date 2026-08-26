# Last Updated : 2026-08-27

"""API 서버의 진입점. uvicorn이 이 파일의 'app' 객체를 찾아 실행한다.

    라우팅 규칙 자체(엔드포링트 함수)는 여기 두지 않고 routes/ 아래 파일로 나눈다.
    main.py는 앱을 조립하고 라우터를 등록하는 역할만 한다.

    *uvicorn은 실제로 TCP 포트를 열고, HTTP 요청을 받아 파싱하여 응답을 돌려보내는 ASGI서버이다.
    FAST API 코드자체는 요청에 따른 함수 콜백만 정의할 뿐, 소켓을 열 능력이 없다.

"""

from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    """서버가 살아있는지 확인하는 Health Check. 배포 환경에서 로드밸런서(load balancer)가 주기적으로 호출"""
    return{"status":"ok"}