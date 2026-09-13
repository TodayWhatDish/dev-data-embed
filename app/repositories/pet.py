# Last updated: 2026-09-13

"""pet 테이블과 그 주변(animal_category, pet_allergy)에 닿는 자리.

단일 테이블 CRUD 는 ORM(session.query/add)으로 간다. 조회가 조인이거나 GROUP_CONCAT 상관
서브쿼리가 섞이면 ORM 표현이 오히려 안 읽혀서 SQL 을 그대로 두고 fetch/fetch_tuples 로 돌린다 —
이름이 코드에 글자로 박혀 있어 general_query 의 화이트리스트가 애초에 필요 없는 자리였다.
"""

import logging

from sqlalchemy.exc import DBAPIError

from app.core.db import as_dict, commit, fetch, fetch_one, fetch_tuples, get_session
from app.models.pet import Breed, Pet, PetAllergy, PetSurvey

logger = logging.getLogger()


def create_pet(
    user_id: int,
    animal_category_id: int,
    name: str,
    gender: str = None,
    birth_date: str = None,
    weight_kg: float = None,
    size: int = None,
    body_type: int = None,
    activity_level: int = None,
) -> int:
    """반려동물 등록. 값이 없는 선택 컬럼은 뺀다 - DB 기본값/NULL 로 채워진다."""
    values = {"user_id": user_id, "animal_category_id": animal_category_id, "name": name}
    for k, v in (
        ("gender", gender),
        ("birth_date", birth_date),
        ("weight_kg", weight_kg),
        ("size", size),
        ("body_type", body_type),
        ("activity_level", activity_level),
    ):
        if v is not None:
            values[k] = v
    pet = Pet(**values)
    session = get_session()
    session.add(pet)
    commit("pet")
    return pet.pet_id


def save_pet_survey(pet_id: int, diet_note: str = None, skin_note: str = None) -> None:
    """가입 설문 스냅샷 저장. 필터가 아니라 추천 질의문 재료 + 관리자 표시용이다
    (docs/schema/pet_schema.md#pet_survey). 갱신은 안 한다 - 가입 시 한 번만 부른다."""
    values = {"pet_id": pet_id}
    for k, v in (("diet_note", diet_note), ("skin_note", skin_note)):
        if v is not None:
            values[k] = v
    get_session().add(PetSurvey(**values))
    commit("pet_survey")


def get_pet_survey(pet_id: int) -> dict | None:
    """펫 한 마리의 설문 스냅샷. 없으면 None (설문을 안 받은 펫)."""
    return fetch_one("SELECT diet_note, skin_note FROM pet_survey WHERE pet_id = ?", (pet_id,))


def get_breeds():
    rows = get_session().query(Breed).all()
    return [as_dict(row) for row in rows]


def find_pets_by_user(user_id: int) -> list[dict]:
    """한 사용자의 (비활성 아닌) 펫 목록. **마스터 이름은 안 붙인다** - id 로만 준다.

    축종/알레르겐은 기동 때 메모리에 올라간 마스터라 조인할 이유가 없다. 이름 붙이기는
    domain.pet.attach_names() 가 캐시로 한다 (docs/WORK.md 2026-09-03 §10).
    쿼리는 그래도 한 방이다 - 관계를 두 번 나눠 읽으면 문장 수가 늘어 그게 더 비싸다.

    알레르겐을 상관 서브쿼리로 뽑는 이유는 pet_allergy 가 다대다여서다. 조인으로 펼치면
    알레르기 수만큼 펫이 중복되고, 부르는 쪽이 다시 묶어야 한다.
    """
    return _fetch_pets("p.user_id = ? AND p.inactive_at IS NULL", (user_id,), f"user_id={user_id}")


def find_pet(pet_id: int) -> dict | None:
    """펫 한 마리. 없으면 None ('없는 id 는 예외가 아니라 None' 이 이 프로젝트의 조회 규약).

    find_pets_by_user 와 **같은 모양**을 준다. 그래야 attach_names() 하나가 둘 다 받는다.
    여기는 inactive_at 을 안 본다 - 비활성 펫도 상세는 열려야 한다.
    """
    rows = _fetch_pets("p.pet_id = ?", (pet_id,), f"pet_id={pet_id}")
    return rows[0] if rows else None


def _fetch_pets(where: str, params: tuple, what: str) -> list[dict]:
    """펫 조회 한 모양. where 는 **코드에 글자로 박힌 것만** 넘긴다 - 사용자 입력은 params 로만 간다"""
    try:
        return fetch(
            f"""
            SELECT p.pet_id, p.name, p.animal_category_id, p.size,
                   (SELECT GROUP_CONCAT(pa.allergen_id)
                      FROM pet_allergy AS pa
                     WHERE pa.pet_id = p.pet_id) AS allergen_ids
              FROM pet AS p
             WHERE {where}
             ORDER BY p.pet_id
        """,
            params,
        )
    except DBAPIError:
        # SQL 에 글자로 박힌 오타나 스키마 변경은 우리 버그다. 어느 조회였는지만 남기고 그대로 올린다
        logger.exception(f"pet 조회 실패: {what}")
        raise


def resolve_allergen_ids(names: list[str]) -> list[int]:
    """알레르겐 이름 목록을 allergen_id 목록으로 바꾼다. DB에 없는 이름은 조용히 빠진다
    (오타로 필터가 통째로 안 걸리는 것보단, 아는 것만이라도 걸리는 게 낫다)."""
    if not names:
        return []
    marks = ", ".join("?" for _ in names)
    rows = fetch_tuples(f"SELECT allergen_id FROM allergen WHERE name_ko IN ({marks})", tuple(names))
    return [row[0] for row in rows]


def add_pet_allergies(pet_id: int, allergen_ids: list[int]) -> None:
    """pet_allergy에 (pet_id, allergen_id) 행을 하나씩 넣는다. 다대다라 여러 행이 나온다."""
    session = get_session()
    for allergen_id in allergen_ids:
        session.add(PetAllergy(pet_id=pet_id, allergen_id=allergen_id))
        commit("pet_allergy")


def find_allergen_names(pet_id: int) -> list[str]:
    """그 펫에게 등록된 알레르겐 이름들. 없으면 빈 목록."""
    try:
        rows = fetch_tuples(
            "SELECT al.name_ko FROM pet_allergy AS pa "
            "JOIN allergen AS al ON al.allergen_id = pa.allergen_id WHERE pa.pet_id = ?",
            (pet_id,),
        )
    except DBAPIError:
        logger.exception(f"pet 알레르기 조회 실패: pet_id={pet_id}")
        raise

    # 튜플을 벗겨서 준다. 부르는 쪽마다 [name for (name,) in ...] 을 반복하지 않게
    return [name for (name,) in rows]
