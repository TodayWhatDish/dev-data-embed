# Last updated: 2026-09-02

""" 사용자 입력(자유 형식)을 searching.candidates()와 recommending.recommend()
    둘 다 받는 dict 형태로 통일하는 자리.
    안 두면 입력 파싱을 두 함수가 각자 다르게 하게 됨.

    DB 에는 repositories/pet.py 를 통해서만 닿는다. 여기에 SQL 이 있으면 스키마가 바뀔 때
    고칠 곳이 features 와 repositories 로 흩어지고, 같은 조인을 두 곳이 다르게 쓰게 된다.
"""

import logging

from typing import Any
from app.domain.common import CommonMgr
from app.domain import pet as pet_domain
from app.repositories import pet as pet_repo
from app.core.config import SIZE_LABELS

logger = logging.getLogger()

def resolve_allergy(raw_text: str) -> str | None:
    """자유 텍스트 안에 등록된 allergen 이름이 있는지 찾고 없다면 필터를 걸지 않는다.
    닭고기를 예로 들때 닭,닭 알러지 같은 입력이 전부 걸리지 않아, 알레르기 필터가 조용히 no-op 됐었다."""
    matches = [
        name for name in CommonMgr.get_inst().get_allergen_names()
        if name in raw_text or raw_text in name
    ]
    if not matches:
        # print 는 로그 파일에 안 남아서, 나중에 '왜 필터가 안 걸렸지' 를 되짚을 수가 없었다
        logger.warning(f"'{raw_text}' 에서 알레르기 항목을 못 찾았습니다 - 필터 미적용")
        return None
    if len(matches) > 1:
        # 첫 번째만 쓰는 건 의도된 동작이지만, 뭘 버렸는지는 남겨둬야 오탐을 추적할 수 있다
        logger.debug(f"'{raw_text}' 에 알레르기 후보 {matches} - '{matches[0]}' 사용")
    return matches[0]

def build_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """자유 형식 입력을 searching.candidates()/recommending.recommend()가 공통으로 쓰는 dict로 통일한다."""
    profile = {}
    if raw.get('animal_category'):
        profile["animal_category"] = raw["animal_category"]
    if raw.get('size_category'):
        profile["size_category"] = raw["size_category"]
    if raw.get("allergy"):
        allergen = resolve_allergy(raw["allergy"])
        if allergen:
            profile["allergy"] = allergen

    logger.debug(f"프로필 조립: {raw} -> {profile}")
    return profile

def list_pets(user_id: int) -> list[dict]:
    """한 사용자의 (비활성 아닌) 펫 목록. 선택지를 보여줄 때 쓴다."""
    # repo 가 id 를 주고 domain 이 캐시로 이름을 붙인다. features 는 둘을 엮기만 한다
    pets = pet_domain.attach_names(pet_repo.find_pets_by_user(user_id))

    # 펫이 없는 것은 에러가 아니다. 다만 '선택지가 왜 비었나' 를 물어볼 때 근거가 있어야 한다
    if not pets:
        logger.info(f"user_id={user_id} 의 활성 펫이 없다")
    logger.debug(f"user_id={user_id} 펫 {len(pets)}마리 조회")
    return pets


def pet_profile(pet_id: int) -> dict[str, Any]:
    """등록된 펫 정보를 그대로 검색 프로필로 만든다.

    사람이 종/체급/알레르기를 다시 타이핑하면 DB에 이미 있는 값을 틀리게 적을 수 있다
    (체급 한 칸을 잘못 고르면 정답이 후보에서 통째로 빠진다). DB 를 단일 출처로 삼는다.
    """
    pet = pet_domain.attach_names_one(pet_repo.find_pet(pet_id))
    if pet is None:
        # 없는 펫은 예외가 아니라 빈 프로필이다 (필터를 안 거는 것과 같아진다).
        # 조용히 넘어가면 '왜 아무 필터도 안 걸렸지' 를 못 찾으니 흔적은 남긴다
        logger.info(f"pet_id={pet_id} 가 없다 - 빈 프로필 반환")
        return {}

    profile = {"animal_category": pet["animal_category"]}
    size = pet["size"]
    if size in SIZE_LABELS:
        # FILTERS["size_category"] 가 SIZE_CASE 로 라벨 비교를 하므로 라벨로 넘긴다.
        # 정수 2 를 그대로 넘기면 '소형' 과 비교돼 아무것도 안 걸린다
        profile["size_category"] = SIZE_LABELS[size]
    else:
        # 라벨이 없는 코드가 들어오면 체급 필터만 조용히 빠진다. 검색 결과가 넓어지는 쪽이라 안 터진다
        logger.warning(f"pet_id={pet_id} 의 size={size!r} 가 SIZE_LABELS 에 없다 - 체급 필터 미적용")

    if pet["allergies"]:
        profile["allergy"] = pet["allergies"]

    logger.debug(f"pet_id={pet_id} 프로필: {profile}")
    return profile
