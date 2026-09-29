# Last Updated: 2026-09-25

"""일반 회원 가입/로그인 - admin_auth.py와 같은 급의 파일이다.

회원가입은 user · pet · pet_allergy · pet_survey 를 한 트랜잭션(core/db.transaction)으로 넣는다 -
중간에 하나라도 실패하면 전부 롤백돼 반쪽 계정이 남지 않는다.
이메일 중복은 미리 조회하지 않고 unique 제약 위반으로 판정한다 - 조회와 insert 사이에
같은 이메일 가입이 끼어드는 경쟁을 DB 가 막아준다.
"""

import secrets

from sqlalchemy.orm import Session

from app.core.db import QueryError, transaction
from app.core.exceptions import Conflict, InvalidInput, Unauthorized
from app.core.security import create_access_token, hash_password, verify_password
from app.domain.common import CommonMgr
from app.repositories import products as product_repo
from app.repositories.pet import add_pet_allergies, create_pet, save_pet_survey
from app.repositories.users import create_user, find_user_by_email
from app.services.purchases import buy, write_review

# animal_category_id 1 = '개'(common_schema.py 시드값). pet_species를 안 주거나 못 찾으면 이 값으로 대체한다.
DOG_CATEGORY_ID = 1
# bcrypt 는 72바이트까지만 받고 넘으면 ValueError 를 던진다(bcrypt 5.x) - 글자 수가 아니라 바이트라 한글은 24자에서 걸린다.
MAX_PASSWORD_BYTES = 72


def register(
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
    """계정 + 펫 프로필을 만들고 user_id 를 돌려준다. 이메일 중복이면 Conflict, 비밀번호가 72바이트를 넘으면 InvalidInput.
    회원가입(signup)과 관리자 회원 추가가 같이 쓴다 - 토큰은 회원가입만 필요하다."""
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise InvalidInput("비밀번호가 너무 깁니다.")
    password_hash = hash_password(password)
    # 축종을 안 주거나 못 찾은 이름이면 기존 동작(강아지)으로 유지 - 하위 호환
    animal_category_id = CommonMgr.get_inst().resolve_animal_category_id(pet_species) or DOG_CATEGORY_ID
    try:
        with transaction(db, "user"):
            user_id = create_user(db, email, name, password_hash, phone, region)
            pet_id = create_pet(
                db,
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
                    add_pet_allergies(db, pet_id, allergen_ids)

            if diet_note or skin_note:
                save_pet_survey(db, pet_id, diet_note, skin_note)
    except QueryError as e:
        # 가입에서 unique 가 걸리는 건 user.email / (auth_provider, auth_uid=email) 뿐이다
        # (알러지 id 는 set 이라 pet_allergy PK 는 안 겹친다)
        if e.reason == "constraint_unique":
            raise Conflict("이미 가입된 이메일입니다.") from e
        raise

    return user_id


def signup(db: Session, email: str, password: str, name: str, pet_name: str, **profile) -> str:
    """회원가입. register() 로 만들고 바로 JWT 를 발급한다. profile 은 register() 의 선택 인자 그대로."""
    return create_access_token("user", str(register(db, email, password, name, pet_name, **profile)))


def login(db: Session, email: str, password: str) -> str:
    """이메일/비밀번호 검증하고 JWT 발급. 틀리면(72바이트 초과 포함) 또는 탈퇴 회원이면 Unauthorized."""
    user = find_user_by_email(db, email)
    if (
        len(password.encode()) > MAX_PASSWORD_BYTES
        or not user
        or user["withdrawn_at"]
        or not user["password_hash"]
        or not verify_password(password, user["password_hash"])
    ):
        raise Unauthorized("이메일 또는 비밀번호가 틀립니다.")
    return create_access_token("user", str(user["user_id"]))


# 시연 계정에 채울 구매 후기 - 알러지(닭고기)와 안 겹치는 상품에 붙인다
POC_REVIEWS = [
    (5, "기호성이 좋아서 한 그릇 다 비웠어요. 변 상태도 괜찮아요."),
    (4, "알갱이가 작아서 먹기 편해 보여요. 재구매 생각 있어요."),
    (3, "처음엔 잘 먹다가 요즘은 조금 남겨요."),
]
# 시연 계정 이름 - 시드 고객(pipeline/make_data/gen_seed.py)처럼 보이게 몇 개만 옮겨 왔다
POC_SURNAMES = "김이박최정강조윤"
POC_GIVEN = ["서연", "민준", "지우", "하은", "도윤", "서준", "수아", "예준"]
POC_PET_NAMES = ["콩이", "보리", "두부", "망고", "모카", "호두", "구름", "라떼"]


def poc_signup(db: Session) -> str:
    """시연용 계정을 바로 만든다: 펫 프로필 + 알러지 + 설문 + 구매/후기 3건까지 채워서 JWT 발급.
    비밀번호는 아무도 모르는 랜덤값이라 이 토큰으로만 들어올 수 있다.
    ponytail: 누를 때마다 계정이 하나씩 쌓인다 - 쌓이는 게 문제가 되면 poc-% 계정 정리 배치를 만든다."""
    user_id = register(
        db,
        f"poc-{secrets.token_hex(4)}@demo.local",
        secrets.token_urlsafe(16),
        secrets.choice(POC_SURNAMES) + secrets.choice(POC_GIVEN),
        secrets.choice(POC_PET_NAMES),
        region="서울",
        pet_species="개",
        pet_gender="F",
        pet_birth_date="2021-05-10",
        pet_weight_kg=4.2,
        pet_size=2,
        pet_activity_level=3,
        pet_allergies=["닭고기"],
        diet_note="입이 짧아 사료를 자주 남겨요",
        skin_note="귀 주변이 가끔 붉어져요",
    )
    dog_ids = {
        r["product_id"]
        for r in product_repo.get_product_animal_category_ids(db)
        if r["animal_category_id"] == DOG_CATEGORY_ID
    }
    products = [
        p
        for p in product_repo.get_products(db)
        if p["product_id"] in dog_ids and "닭" not in p["name"] and "치킨" not in p["name"]
    ]
    for product, (rating, body) in zip(
        secrets.SystemRandom().sample(products, len(POC_REVIEWS)), POC_REVIEWS
    ):
        write_review(db, user_id, buy(db, user_id, product["product_id"])["purchase_id"], rating, body)
    return create_access_token("user", str(user_id))
