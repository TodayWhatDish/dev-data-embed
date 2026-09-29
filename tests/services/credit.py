"""구매 크레딧 차감을 본다.

1) 잔액보다 큰 금액은 차감되지 않는다(None).
2) 잔액을 다 쓴 회원이 사면 Conflict 이고 구매 행이 생기지 않는다.
끝에 롤백해서 DB 에 흔적을 남기지 않는다.

    py -m tests.services.credit
"""

from app.core.db import fetch_one, new_session
from app.core.exceptions import Conflict
from app.domain.domain_init import init_from_db
from app.repositories.users import spend_credit
from app.services.purchases import buy

if __name__ == "__main__":
    db = new_session()
    init_from_db(db)
    user = fetch_one(
        db,
        'SELECT u.user_id, u.credit_krw FROM "user" AS u JOIN pet AS pe ON pe.user_id = u.user_id LIMIT 1',
    )
    product_id = fetch_one(db, "SELECT product_id FROM product WHERE price_krw > 0 LIMIT 1")["product_id"]
    count_sql = "SELECT count(*) AS n FROM purchase AS pu JOIN pet AS pe ON pe.pet_id = pu.pet_id WHERE pe.user_id = %s"
    before = fetch_one(db, count_sql, (user["user_id"],))["n"]
    try:
        assert spend_credit(db, user["user_id"], user["credit_krw"] + 1) is None, "잔액보다 큰 금액이 차감됐다"
        assert spend_credit(db, user["user_id"], user["credit_krw"]) == 0, "잔액 전부 차감 실패"
        try:
            buy(db, user["user_id"], product_id)
            raise AssertionError("잔액 0 인데 구매됐다")
        except Conflict as e:
            assert "크레딧" in e.msg, e.msg
        assert fetch_one(db, count_sql, (user["user_id"],))["n"] == before, "실패한 구매 행이 남았다"
    finally:
        db.rollback()
        db.close()
    print("ok")
