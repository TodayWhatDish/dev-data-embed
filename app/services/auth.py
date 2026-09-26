# Last Updated: 2026-09-25

"""일반 회원 가입/로그인 - admin_auth.py와 같은 급의 파일이다.

회원가입은 user · pet · pet_allergy · pet_survey 를 한 트랜잭션(core/db.transaction)으로 넣는다 -
중간에 하나라도 실패하면 전부 롤백돼 반쪽 계정이 남지 않는다.
이메일 중복은 미리 조회하지 않고 unique 제약 위반으로 판정한다 - 조회와 insert 사이에
같은 이메일 가입이 끼어드는 경쟁을 DB 가 막아준다.
"""

from app.core.db import QueryError, transaction
from app.core.exceptions import Conflict, InvalidInput, Unauthorized
from app.core.security import create_access_token, hash_password, verify_password
from app.domain.common import CommonMgr
from app.repositories.pet import add_pet_allergies, create_pet, save_pet_survey
from app.repositories.users import create_user, find_user_by_email

# animal_category_id 1 = '개'(common_schema.py 시드값). pet_species를 안 주거나 못 찾으면 이 값으로 대체한다.
DOG_CATEGORY_ID = 1
# bcrypt 는 72바이트까지만 받고 넘으면 ValueError 를 던진다(bcrypt 5.x) - 글자 수가 아니라 바이트라 한글은 24자에서 걸린다.
MAX_PASSWORD_BYTES = 72


def signup(
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
    """이메일 중복이면 Conflict. 비밀번호가 72바이트를 넘으면 InvalidInput.
    통과하면 계정 + 강아지 펫 프로필을 만들고 바로 JWT를 발급한다."""
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise InvalidInput("비밀번호가 너무 깁니다.")
    password_hash = hash_password(password)
    # 축종을 안 주거나 못 찾은 이름이면 기존 동작(강아지)으로 유지 - 하위 호환
    animal_category_id = CommonMgr.get_inst().resolve_animal_category_id(pet_species) or DOG_CATEGORY_ID
    try:
        with transaction("user"):
            user_id = create_user(email, name, password_hash, phone, region)
            pet_id = create_pet(
                user_id,
                animal_category_id,
                pet_name,
                gender=pet_gender,
                birth_date=pet_birth_date,
                weight_kg=pet_weight_kg,
                size=pet_size,
                activity_level=pet_activity_level,
            )

            if pet_allergies:
                allergen_ids = CommonMgr.get_inst().resolve_allergen_ids(pet_allergies)
                if allergen_ids:
                    add_pet_allergies(pet_id, allergen_ids)

            if diet_note or skin_note:
                save_pet_survey(pet_id, diet_note, skin_note)
    except QueryError as e:
        # 가입에서 unique 가 걸리는 건 user.email / (auth_provider, auth_uid=email) 뿐이다
        # (알러지 id 는 set 이라 pet_allergy PK 는 안 겹친다)
        if e.reason == "constraint_unique":
            raise Conflict("이미 가입된 이메일입니다.") from e
        raise

    return create_access_token("user", str(user_id))


def login(email: str, password: str) -> str:
    """이메일/비밀번호 검증하고 JWT 발급. 틀리면(72바이트 초과 포함) Unauthorized."""
    user = find_user_by_email(email)
    if (
        len(password.encode()) > MAX_PASSWORD_BYTES
        or not user
        or not user["password_hash"]
        or not verify_password(password, user["password_hash"])
    ):
        raise Unauthorized("이메일 또는 비밀번호가 틀립니다.")
    return create_access_token("user", str(user["user_id"]))
