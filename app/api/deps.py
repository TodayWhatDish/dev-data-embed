"""라우트가 Depends()로 받는 것들. HTTP 헤더를 읽으므로 core가 아니라 api 층에 둔다."""

import threading
import time
from collections import defaultdict, deque

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import JWT_ALGORITHM, JWT_SECRET

# auto_error=False: 토큰이 없을 때도 아래 _decode_token이 401과 한국어 메시지를 준다.
# HTTPBearer를 쓰면 /docs에 Authorize 버튼이 생긴다.
bearer = HTTPBearer(auto_error=False)


def _decode_token(credentials: HTTPAuthorizationCredentials | None, expected_role: str) -> dict:
    """Bearer <jwt> 를 검증하고 payload를 돌려준다. role이 안 맞거나 실패하면 401."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("role") != expected_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{expected_role} 권한이 없는 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_current_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> int:
    """admin 역할 토큰인지 확인한다. 실패하면 401.
    관리자는 공용 비밀번호라 계정별 id가 없다 - 통과 여부만 의미 있다."""
    _decode_token(credentials, "admin")


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> int:
    """user 역할 토큰을 검증하고 user_id를 돌려준다. 실패하면 401."""
    payload = _decode_token(credentials, "user")
    return int(payload["sub"])


def rate_limit(times: int, seconds: int):
    """IP마다 seconds초 안에 times번까지. 넘으면 429. 부를 때마다 따로 세는 통이 생긴다(라우트별 한도).

    ponytail: 프로세스 메모리에 센다 - 워커가 1개(uvicorn 기본)일 때만 정확하고, 재시작하면 초기화되며,
    IP 키는 지우지 않아 접속 IP 수만큼 조금씩 커진다. 워커를 늘리거나 서버가 여러 대가 되면 Redis 기반(slowapi 등)으로.
    Railway 프록시 뒤라 진짜 IP 는 X-Forwarded-For 에 있다 - Dockerfile 의 --forwarded-allow-ips 가 그걸 client.host 로 풀어준다.
    """
    hits: dict[str, deque] = defaultdict(deque)
    lock = threading.Lock()  # 동기 의존성이라 스레드풀에서 동시에 불린다

    def check(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with lock:
            recent = hits[ip]
            while recent and now - recent[0] >= seconds:
                recent.popleft()
            if len(recent) >= times:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
                    headers={"Retry-After": str(seconds)},
                )
            recent.append(now)

    return check
