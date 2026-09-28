# Last Updated : 2026-09-27

"""로그인/질문 엔드포인트의 호출 횟수 제한. 넘으면 429.

로그인은 비밀번호 대입을, /ask 는 LLM 요금 폭주를 막는 게 목적이다.
프로세스 메모리에 IP별 최근 호출 시각만 들고 있는 슬라이딩 윈도우라 외부 의존성이 없다 -
대신 워커/인스턴스끼리 카운트를 공유하지 않는다(워커 N개면 실효 한도가 N배). 여러 대로
늘리면 Redis 같은 공유 저장소로 옮길 것.

라우트가 sync 라 스레드풀에서 동시에 불린다 - 기록 갱신은 Lock 안에서 한다.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import ASK_LIMIT_SECONDS, ASK_LIMIT_TIMES, LOGIN_LIMIT_SECONDS, LOGIN_LIMIT_TIMES


class RateLimit:
    """Depends(RateLimit(5, 60)) 처럼 라우트에 건다. 같은 IP 가 seconds 안에 times 번을 넘으면 429."""

    def __init__(self, times: int, seconds: int):
        self.times = times
        self.seconds = seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        # Dockerfile 의 --proxy-headers 덕에 프록시 뒤에서도 client.host 가 실제 클라이언트 IP 다
        key = f"{request.url.path}:{request.client.host if request.client else '-'}"
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.seconds:
                hits.popleft()
            if len(hits) >= self.times:
                retry_after = int(self.seconds - (now - hits[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)


# 한도 값과 근거는 config.py 에 있다
login_limit = RateLimit(times=LOGIN_LIMIT_TIMES, seconds=LOGIN_LIMIT_SECONDS)
ask_limit = RateLimit(times=ASK_LIMIT_TIMES, seconds=ASK_LIMIT_SECONDS)
