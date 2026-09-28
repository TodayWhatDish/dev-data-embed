"""고객 상세를 조립하는 자리. repositories 가 읽고 domain 이 가공하는 순서를 여기서 엮는다.

get_user_detail() 을 라우트가 직접 부르던 걸 여기로 모았다. 구매이력의 사료/간식 구분처럼
**마스터 캐시를 봐야 아는 값**이 붙는 곳이 한 군데여야, 새 호출자가 그걸 빠뜨리지 않는다.
"""

import logging

from sqlalchemy.orm import Session

from app.core.db import QueryError, transaction
from app.core.exceptions import InvalidInput, NotFound
from app.domain import products as product_domain
from app.domain.common import CommonMgr
from app.repositories import pet as pet_repo
from app.repositories import users as users_repo
from app.services.auth import register
from app.services.products import CLIENT_FAULT

logger = logging.getLogger()

# CustomerUpdate 필드 -> 어느 테이블 어느 컬럼인지. pet_allergies 는 다대다라 따로 간다
USER_COLUMNS = {"name": "name", "email": "email", "phone": "phone", "region": "region"}
PET_COLUMNS = {
    "pet_name": "name",
    "pet_gender": "gender",
    "pet_birth_date": "birth_date",
    "pet_weight_kg": "weight_kg",
    "pet_size": "size",
    "pet_neutered": "neutered",
    "pet_activity_level": "activity_level",
}
SURVEY_COLUMNS = {"diet_note": "diet_note", "skin_note": "skin_note"}


def customer_list(db: Session) -> list[dict]:
    """관리자 고객 목록."""
    return users_repo.list_users(db)


def customer_detail(db: Session, user_id: int) -> dict | None:
    """고객 프로필 + 반려동물 + 구매이력. 없는 고객은 예외가 아니라 None."""
    detail = users_repo.get_user_detail(db, user_id)
    if detail is None:
        logger.info(f"user_id={user_id} 가 없다")
        return None

    # repo 는 product_category_id 까지만 준다. 사료/간식으로 접는 건 분류 트리를 걸어야 하는
    # 일이라 캐시를 가진 domain 이 한다 (docs/WORK.md 2026-09-03 §11)
    detail["purchases"] = product_domain.attach_product_type(detail["purchases"])
    return detail


def create_customer(db: Session, values: dict) -> dict:
    """관리자 회원 추가. 회원가입과 같은 register() 를 탄다 - 계정 + 첫 펫 + 알러지 + 설문이 한 트랜잭션이다."""
    user_id = register(db, **values)
    logger.info(f"관리자 회원 추가: user_id={user_id}")
    return customer_detail(db, user_id)


def _pick(values: dict, columns: dict[str, str]) -> dict:
    return {column: values[field] for field, column in columns.items() if field in values}


def update_customer(db: Session, user_id: int, values: dict) -> dict:
    """계정 + 펫 한 마리 + 설문 + 알러지를 한 트랜잭션으로 고친다. 준 필드만 바꾼다.
    없는 고객, 이 고객 것이 아닌 pet_id 는 NotFound. 이메일 중복은 Conflict."""
    if not values:  # PATCH 빈 바디
        raise InvalidInput("고칠 값이 없습니다.")
    pet_id = values.get("pet_id")
    user_values = _pick(values, USER_COLUMNS)
    pet_values = _pick(values, PET_COLUMNS)
    survey_values = _pick(values, SURVEY_COLUMNS)
    touches_pet = bool(pet_values or survey_values or "pet_allergies" in values)
    if touches_pet and pet_id is None:
        raise InvalidInput("반려동물 정보를 고치려면 pet_id 가 필요합니다.")

    try:
        with transaction(db, "user"):
            if users_repo.update_user(db, user_id, user_values) == 0:
                raise NotFound(f"user_id {user_id} 고객이 없습니다.")
            if touches_pet:
                if pet_repo.update_pet(db, pet_id, user_id, pet_values) == 0:
                    raise NotFound(f"이 고객의 반려동물(pet_id {pet_id})이 없습니다.")
                if survey_values:
                    pet_repo.upsert_pet_survey(db, pet_id, survey_values)
                if "pet_allergies" in values:
                    allergen_ids = CommonMgr.get_inst().resolve_allergen_ids(values["pet_allergies"] or [])
                    pet_repo.replace_pet_allergies(db, pet_id, allergen_ids)
    except QueryError as e:
        fault = CLIENT_FAULT.get(e.reason)
        if fault is None:
            raise  # 서버 버그 -> 500 + 트레이스백
        exc_cls, msg = fault
        raise exc_cls(msg) from e

    logger.info(f"관리자 회원 수정: user_id={user_id}, fields={sorted(values)}")
    return customer_detail(db, user_id)


def withdraw_customer(db: Session, user_id: int) -> None:
    """탈퇴 처리(withdrawn_at). 목록에서 빠지고 로그인이 막힌다. 구매 이력은 남는다.
    없는 고객이거나 이미 탈퇴했으면 NotFound."""
    with transaction(db, "user"):
        if users_repo.withdraw_user(db, user_id) == 0:
            raise NotFound(f"탈퇴 처리할 user_id {user_id} 고객이 없습니다.")
    logger.info(f"관리자 회원 탈퇴 처리: user_id={user_id}")
