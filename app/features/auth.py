# Last updated: 2026-09-03
# Last Updated : 2026-09-03

"""일반 회원 가입/로그인 - admin_auth.py와 같은 급의 파일이다.

회원가입은 계정(user) + 반려동물(pet) 두 행을 만든다. 두 insert는 각자 따로 커밋된다
(app/core/db.py의 execute()가 호출마다 커밋) - user는 만들어졌는데 pet insert만 실패하는
경우가 이론적으로 남는다. 이 프로젝트 규모에선 감내하고, 문제되면 트랜잭션으로 묶을 것.
"""

import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

from app.core.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES
from app.repositories.users import find_user_by_email, create_user
from app.repositories.pet import create_pet

# animal_category_id 1 = '개'(common_schema.py 시드값). 회원가입 시점엔 강아지 프로필만 받는다.
DOG_CATEGORY_ID = 1


def _issue_token(user_id: int) -> str:
    """user_id를 담아 JWT를 발급한다. signup/login 둘 다 여기로 모은다."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode(
        {"role": "user", "sub": str(user_id), "exp": expire},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def signup(email: str, password: str, name: str, pet_name: str,
           phone: str | None = None, region: str | None = None,
           pet_gender: str | None = None, pet_birth_date: str | None = None,
           pet_weight_kg: float | None = None) -> str:
    """이메일 중복이면 ValueError. 통과하면 계정 + 강아지 펫 프로필을 만들고 바로 JWT를 발급한다."""
    if find_user_by_email(email):
        raise ValueError("이미 가입된 이메일입니다.")

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = create_user(email, name, password_hash, phone, region)
    create_pet(user_id, DOG_CATEGORY_ID, pet_name,
               gender=pet_gender, birth_date=pet_birth_date, weight_kg=pet_weight_kg)
    return _issue_token(user_id)


def login(email: str, password: str) -> str:
    """이메일/비밀번호 검증하고 JWT 발급. 틀리면 ValueError."""
    user = find_user_by_email(email)
    if not user or not user["password_hash"] or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        raise ValueError("이메일 또는 비밀번호가 틀립니다.")
    return _issue_token(user["user_id"])
