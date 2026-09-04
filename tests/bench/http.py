"""서버에 실제 HTTP 부하를 걸어 용량을 잰다 (open-loop).

다른 벤치들은 함수를 직접 부른다. 여기만 uvicorn 을 띄워놓고 소켓으로 때린다 —
FastAPI 워커 풀, JSON 직렬화, 인증까지 다 포함된 '진짜' 숫자를 보는 자리다.

**open-loop 인 게 요점이다.** 게임 스트레스 봇처럼 '응답 받고 다음 요청' 으로 짜면(closed-loop)
서버가 느려질 때 봇도 같이 느려져서 부하가 저절로 줄어든다 - 서버가 죽어가는데 숫자는 멀쩡해 보인다
(coordinated omission). 그래서 여기선 응답을 안 기다리고 **정해진 간격으로 계속 쏜다.**
서버가 못 따라오면 그건 지연에 쌓인다.

보는 건 평균이 아니라 p95/p99 다. 평균은 느린 1%를 빠른 99%가 덮어버려서, 실제로 화가 난
사용자가 몇 명인지 안 보여준다. 목표 RPS 를 계단식으로 올리다가 **p99 가 꺾이는 지점이 용량**이다.

    uvicorn app.main:app          # 먼저 다른 창에서
    python -m tests.bench.http    # 그 다음 여기

    python -m tests.bench.http /health 50 100 200 300

/health 외에는 전부 관리자 전용이라 시작할 때 .env 의 ADMIN_PASSWORD 로 한 번 로그인해
토큰을 붙인다. BODIES 에 있는 경로는 POST + 그 JSON 바디로 쏘고, 없으면 GET 이다.

**/ask 와 /recommend 는 LLM 을 부른다.** 400 RPS 로 3초면 API 호출 1200번이고 그만큼 요금이 나온다.
그 둘은 STAGES 를 1~5 정도로 낮춰서 부른다:  python -m tests.bench.http /recommend 1 2 5

실발사량이 목표보다 한참 모자라거나 PoolTimeout 이 뜨면 그 줄은 서버가 아니라 이 도구를 잰 값이다.
"""
import asyncio
import os
import statistics
import sys
import time

import httpx

from app.core.config import ADMIN_PASSWORD

BASE = 'http://127.0.0.1:8000'
# 미처리 요청 한계. 넘으면 서버가 못 따라온다는 뜻이라 그 스테이지를 끊는다.
# 안 끊으면 쌓인 요청이 다음 스테이지까지 섞여서 어느 부하의 숫자인지 알 수 없게 된다
MAX_INFLIGHT = 1000
STAGES = (50, 100, 200, 400)      # 목표 RPS. 꺾이는 데가 안 나오면 더 올려서 다시 돌린다
SECONDS = 3

# 여기 있는 경로는 POST + 이 바디로 쏜다. 없으면 GET.
# 부하마다 같은 바디를 쓴다 - 질의를 바꾸면 무엇을 쟀는지 알 수 없게 된다
BODIES = {
    '/recommend': {'user_query': '알러지 없는 사료 추천해줘', 'animal_category': '개', 'n_pick': 3},
    '/ask': {'user_query': '우리 애가 먹을 만한 사료 있어?', 'pet_id': 1},
}


async def fire(client, path, out, live):
    """한 발. 결과는 (지연 ms, 상태) 로 남긴다. 예외도 상태로 취급해 같이 센다"""
    began = time.perf_counter()
    try:
        body = BODIES.get(path)
        res = await (client.post(path, json=body) if body else client.get(path))
        out.append(((time.perf_counter() - began) * 1000, res.status_code))
    except Exception as e:                          # noqa: BLE001 - 타임아웃/거절 전부 실패다
        out.append(((time.perf_counter() - began) * 1000, type(e).__name__))
    finally:
        live[0] -= 1


async def stage(client, path, rps, seconds):
    """rps 로 seconds 동안 쏜다. 응답을 안 기다리고 다음 발을 쏘는 게 open-loop 다.

    발사 시각을 i/rps 로 미리 정해두고 그 시각에 맞춰 재운다. '한 발 쏘고 1/rps 초 대기' 로 짜면
    요청 만드는 시간이 간격에 누적돼서 실제 발사량이 목표보다 계속 모자라게 된다.
    """
    out, tasks, live = [], [], [0]
    start = time.perf_counter()
    lag, full = 0.0, False
    for i in range(int(rps * seconds)):
        due = start + i / rps
        late = time.perf_counter() - due
        if late < 0:
            await asyncio.sleep(-late)
        else:
            lag = max(lag, late)                    # 부하 도구가 못 따라간 정도. 크면 숫자를 믿으면 안 된다
        if live[0] >= MAX_INFLIGHT:
            full = True                             # 응답이 안 돌아와 쌓였다 = 이 부하는 이미 감당 밖이다
            break
        live[0] += 1
        tasks.append(asyncio.create_task(fire(client, path, out, live)))

    fired = time.perf_counter() - start
    await asyncio.gather(*tasks)                    # 남은 응답까지 다 받고 나서 집계한다
    return out, fired, lag, full


def report(rps, out, fired, lag, full):
    oks = sorted(ms for ms, st in out if st == 200)
    bad = {}
    for _ms, st in out:
        if st != 200:
            bad[st] = bad.get(st, 0) + 1

    if not oks:
        print(f'  {rps:>5} RPS  전부 실패 {bad}')
        return None

    pct = lambda p: oks[min(len(oks) - 1, int(len(oks) * p))]
    print(f'  {rps:>5} RPS  실발사 {len(out) / fired:6.1f}/s  '
          f'p50 {statistics.median(oks):7.1f}  p95 {pct(0.95):8.1f}  p99 {pct(0.99):8.1f} ms  '
          f'실패 {sum(bad.values()):>4}{"  " + str(bad) if bad else ""}'
          f'{"   [포화: 미처리 " + str(MAX_INFLIGHT) + " 돌파]" if full else ""}'
          f'{f"   [발사지연 {lag * 1000:.0f}ms]" if lag > 0.05 else ""}')
    return pct(0.99)


async def login(client):
    """관리자 토큰을 받아 헤더에 박는다. /health 만 잴 거면 없어도 되니 실패해도 안 죽는다"""
    pw = os.environ.get('ADMIN_PASSWORD') or ADMIN_PASSWORD
    if not pw:
        print('  ADMIN_PASSWORD 가 없다. /health 외 경로는 401 이 뜬다')
        return
    res = await client.post('/admin/login', json={'password': pw})
    if res.status_code != 200:
        print(f'  로그인 실패 {res.status_code} {res.text[:80]} - 인증 경로는 401 이 뜬다')
        return
    client.headers['Authorization'] = f'Bearer {res.json()["access_token"]}'


async def main(path, stages):
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as client:
        try:
            await client.get('/health')
        except httpx.ConnectError:
            sys.exit(f'서버가 없다. 먼저 띄운다:  uvicorn app.main:app   ({BASE})')
        await login(client)

        print()
        print(f'{path}  (스테이지당 {SECONDS}초, open-loop)')
        knee, base, full_stop = None, None, [False]
        for rps in stages:
            got = await stage(client, path, rps, SECONDS)
            p99 = report(rps, *got)
            full_stop = [got[3]]
            if full_stop[0]:
                knee = knee or rps
                break
            if p99 is None:
                sys.exit(f'  {path} 가 200 을 하나도 안 준다. 경로와 인증을 먼저 본다')
            base = base or p99
            # p99 가 첫 스테이지의 3배를 넘으면 거기가 무릎이다. 그 아래까지가 감당 가능한 부하
            if knee is None and p99 > base * 3:
                knee = rps

        print()
        print('  용량: ' + (f'{knee} RPS 에서 p99 가 꺾인다 (그 아래까지 감당)' if knee
                          else f'{stages[-1]} RPS 까지 안 꺾임 - 더 올려서 다시 잰다'))


if __name__ == '__main__':
    args = sys.argv[1:]
    path = args[0] if args else '/health'
    asyncio.run(main(path, tuple(int(a) for a in args[1:]) or STAGES))
