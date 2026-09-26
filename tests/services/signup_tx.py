"""회원가입이 한 트랜잭션인지 본다 (BE-12).

1) 마지막 단계(알러지 저장)에서 터지면 앞서 넣은 user · pet 까지 전부 롤백돼야 한다 - 반쪽 계정 금지.
2) 이미 있는 이메일은 사전 조회 없이 unique 제약 위반으로 Conflict 가 돼야 한다.
둘 다 롤백으로 끝나 행이 남지 않는다(시퀀스 번호만 하나씩 소모된다).

    py -m tests.services.signup_tx
"""

from app.core.db import fetch_one
from app.core.exceptions import Conflict
from app.domain.domain_init import init_from_db
from app.repositories.users import find_user_by_email
from app.services import auth

EMAIL = "__test_signup_tx__@example.com"

if __name__ == "__main__":
    init_from_db()
    assert find_user_by_email(EMAIL) is None, "이전 실행의 흔적이 남아있다"

    def boom(*_):
        raise RuntimeError("알러지 저장 실패 흉내")

    original, auth.add_pet_allergies = auth.add_pet_allergies, boom
    try:
        auth.signup(EMAIL, "pw12345", "트랜잭션테스트", "테스트펫", pet_allergies=["닭고기"])
        raise AssertionError("예외가 안 났다")
    except RuntimeError:
        pass
    finally:
        auth.add_pet_allergies = original
    assert find_user_by_email(EMAIL) is None, "알러지 단계 실패인데 user 가 남았다"

    existing = fetch_one('SELECT email FROM "user" WHERE email IS NOT NULL LIMIT 1')["email"]
    try:
        auth.signup(existing, "pw12345", "중복", "중복펫")
        raise AssertionError("중복 이메일인데 가입됐다")
    except Conflict:
        pass
    print("ok")
