# Last updated: 2026-09-03
# Last Updated : 2026-09-03

"""일반 회원 가입/로그인 - admin_auth.py와 같은 급의 파일이다.

회원가입은 계정(user) + 반려동물(pet) + 알러지 + 설문을 한 트랜잭션으로 만든다. repositories 는
flush 만 하고 커밋은 signup() 이 마지막에 한 번 한다 - 중간에 실패하면 user 만 남는 일이 없다.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy.orm import Session

from app.core.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from app.core.db import QueryError, commit
from app.domain.common import CommonMgr
from app.repositories.pet import add_pet_allergies, create_pet, save_pet_survey
from app.repositories.users import create_user, find_user_by_email

# animal_category_id 1 = '개'(common_schema.py 시드값). pet_species를 안 주거나 못 찾으면 이 값으로 대체한다.
DOG_CATEGORY_ID = 1


def _issue_token(user_id: int) -> str:
    """user_id를 담아 JWT를 발급한다. signup/login 둘 다 여기로 모은다."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode(
        {"role": "user", "sub": str(user_id), "exp": expire},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def signup(
    db: Session,
    email: str,
    password: str,
    name: str,
    pet_name: str,
    phone: str | None = None,
    region: str | None = None,
    pet_gender: str | None = None,
    pet_birth_date: str | None = None,
    pet_weight_kg: float | None = None,
    pet_size: int | None = None,
    pet_activity_level: int | None = None,
    pet_allergies: list[str] | None = None,
    diet_note: str | None = None,
    skin_note: str | None = None,
    pet_species: str | None = None,
) -> str:
    """이메일 중복이면 ValueError. 통과하면 계정 + 펫 프로필을 만들고 바로 JWT를 발급한다.

    중복은 미리 SELECT 하지 않고 user 의 UNIQUE 위반으로 판정한다 - 조회와 INSERT 사이에
    같은 이메일 가입이 끼어들면 SELECT 로는 못 막는다.
    """
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    # 축종을 안 주거나 못 찾은 이름이면 기존 동작(강아지)으로 유지 - 하위 호환
    animal_category_id = CommonMgr.get_inst().resolve_animal_category_id(pet_species) or DOG_CATEGORY_ID
    allergen_ids = CommonMgr.get_inst().resolve_allergen_ids(pet_allergies) if pet_allergies else []

    # user -> pet -> 알러지 -> 설문을 flush 로 쌓고 마지막에 한 번 커밋한다
    try:
        user_id = create_user(db, email, name, password_hash, phone, region)
        pet_id = create_pet(db,
            user_id,
            animal_category_id,
            pet_name,
            gender=pet_gender,
            birth_date=pet_birth_date,
            weight_kg=pet_weight_kg,
            size=pet_size,
            activity_level=pet_activity_level,
        )
        if allergen_ids:
            add_pet_allergies(db, pet_id, allergen_ids)
        if diet_note or skin_note:
            save_pet_survey(db, pet_id, diet_note, skin_note)
        commit(db, "signup")
    except QueryError as e:
        # flush/commit 이 이미 롤백했다
        if e.reason == "constraint_unique" and e.table == "user":
            raise ValueError("이미 가입된 이메일입니다.") from e
        raise

    return _issue_token(user_id)


def login(db: Session, email: str, password: str) -> str:
    """이메일/비밀번호 검증하고 JWT 발급. 틀리면 ValueError."""
    user = find_user_by_email(db, email)
    if (
        not user
        or not user["password_hash"]
        or not bcrypt.checkpw(password.encode(), user["password_hash"].encode())
    ):
        raise ValueError("이메일 또는 비밀번호가 틀립니다.")
    return _issue_token(user["user_id"])
