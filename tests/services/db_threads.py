"""커넥션이 스레드마다 따로인지 본다.

라우트가 전부 `def`(= async 아님)라 FastAPI 는 동시 요청을 스레드풀에서 돌린다. 예전처럼
커넥션 하나를 `check_same_thread=False` 로 열어 다 같이 쓰면, 같은 커넥션을 여러 스레드가
동시에 execute 하다가 파이썬 sqlite3 모듈의 커넥션 내부 상태가 깨진다 —
`InterfaceError: bad parameter or other API misuse` 로 4스레드 12,000회 중 1,121회가 터졌다.

**혼자 눌러보면 절대 안 나오는 종류의 버그다.** 그래서 자체검증으로 남긴다.
읽기만 하므로 DB 를 안 건드린다.

    py -m tests.services.db_threads
"""

import threading

from app.core.db import fetch, new_session

THREADS, LOOPS = 4, 1500


def hammer(errors, done):
    """repositories 가 실제로 쓰는 경로 그대로 두들긴다. 요청 하나 = 세션 하나(get_db)처럼 스레드마다 세션을 연다"""
    with new_session() as db:
        for _ in range(LOOPS):
            try:
                fetch(db, "SELECT pet_id, name FROM pet WHERE user_id = %s", (1,))
                fetch(db, "SELECT pet_id FROM pet WHERE user_id = %s", (1,))
                done.append(1)
            except Exception as e:  # noqa: BLE001 - 무슨 예외든 여기선 실패다
                errors.append(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    # 동시에 두들겨도 하나도 안 터져야 한다. 예전 구조에선 여기서 9% 가 실패했다
    errors, done = [], []
    workers = [threading.Thread(target=hammer, args=(errors, done)) for _ in range(THREADS)]
    [t.start() for t in workers]
    [t.join() for t in workers]

    kinds = {}
    for e in errors:
        kinds[e] = kinds.get(e, 0) + 1
    print(f"{THREADS}스레드 x {LOOPS}회: 성공 {len(done):,} / 실패 {len(errors):,} {kinds or ''}")
    assert not errors, f"동시 조회가 실패했다: {kinds}"
    assert len(done) == THREADS * LOOPS

    print("ok")
