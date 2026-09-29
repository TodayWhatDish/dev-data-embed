"""/ask/me 하루 질문 한도를 본다.

1) 오늘 질문이 ASK_DAILY_MAX 개 쌓이면 남은 수가 0 이다.
2) 어제 이전 질문은 세지 않는다.
flush 만 하고 끝에 롤백해서 DB 에 흔적을 남기지 않는다.

    py -m tests.services.ask_quota
"""

from app.core.config import ASK_DAILY_MAX
from app.core.db import fetch_one, new_session
from app.services.questions import questions_left_today


def add(db, user_id: int, created_at: str | None = None) -> None:
    """질문 한 건을 커밋 없이 넣는다. created_at 을 안 주면 DB 기본값(지금)."""
    fetch_one(
        db,
        "INSERT INTO customer_question (user_id, user_query, ok, created_at) "
        "VALUES (%s, '한도 점검', true, COALESCE(%s, to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))) "
        "RETURNING question_id",
        (user_id, created_at),
    )


if __name__ == "__main__":
    db = new_session()
    try:
        user_id = fetch_one(db, 'SELECT user_id FROM "user" ORDER BY user_id LIMIT 1')["user_id"]
        start = questions_left_today(db, user_id)  # 오늘 이미 물었으면 ASK_DAILY_MAX 보다 작다

        add(db, user_id, created_at="2000-01-01 00:00:00")
        assert questions_left_today(db, user_id) == start, "오래된 질문까지 셌다"

        for _ in range(start):
            add(db, user_id)
        assert questions_left_today(db, user_id) == 0, "한도만큼 물었는데 남은 수가 0 이 아니다"

        add(db, user_id)
        assert questions_left_today(db, user_id) == 0, "한도를 넘으면 음수가 아니라 0 이어야 한다"
        assert 0 <= start <= ASK_DAILY_MAX
    finally:
        db.rollback()
        db.close()
    print("ok")
