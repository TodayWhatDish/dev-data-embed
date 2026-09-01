# Last updated: 2026-08-31

""" 사용자 입력(자유 형식)을 searching.candidates()와 recommending.recommend()
    둘 다 받는 dict 형태로 통일하는 자리.
    안 두면 입력 파싱을 두 함수가 각자 다르게 하게 됨.
"""

from typing import Any
from app.domain.common import CommonMgr
from app.core.db import query, one, dicts
from app.core.config import SIZE_LABELS

def resolve_allergy(raw_text: str) -> str | None:
    """자유 텍스트 안에 등록된 allergen 이름이 있는지 찾고 없다면 필터를 걸지 않는다. 
    닭고기를 예로 들때 닭,닭 알러지 같은 입력이 전부 걸리지 않아, 알레르기 필터가 조용히 no-op 됐었다."""
    matches = [
        name for name in CommonMgr.get_inst().get_allergen_names()
        if name in raw_text or raw_text in name
    ]
    if not matches:
        print(f"[경고 ] '{raw_text}'에서 알레르기 항목을 못 찾았습니다 - 필터 미적용")
        return None
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
    return profile

def list_pets(user_id: int) -> list[dict]:
    """한 사용자의 (비활성 아닌) 펫 목록. 선택지를 보여줄 때 쓴다."""
    return dicts("""
        SELECT p.pet_id, p.name, ac.name_ko AS animal_category, p.size,
               (SELECT GROUP_CONCAT(al.name_ko)
                  FROM pet_allergy AS pa
                  JOIN allergen AS al ON al.allergen_id = pa.allergen_id
                 WHERE pa.pet_id = p.pet_id) AS allergies
          FROM pet AS p
          JOIN animal_category AS ac ON ac.animal_category_id = p.animal_category_id
         WHERE p.user_id = ? AND p.inactive_at IS NULL
         ORDER BY p.pet_id
    """, (user_id,))


def pet_profile(pet_id: int) -> dict[str, Any]:
    """등록된 펫 정보를 그대로 검색 프로필로 만든다.

    사람이 종/체급/알레르기를 다시 타이핑하면 DB에 이미 있는 값을 틀리게 적을 수 있다
    (체급 한 칸을 잘못 고르면 정답이 후보에서 통째로 빠진다). DB 를 단일 출처로 삼는다.
    """
    row = one("""
        SELECT ac.name_ko AS animal_category, p.size
          FROM pet AS p
          JOIN animal_category AS ac ON ac.animal_category_id = p.animal_category_id
         WHERE p.pet_id = ?
    """, (pet_id,))
    if row is None:
        return {}

    animal_category, size = row
    profile = {"animal_category": animal_category}
    if size in SIZE_LABELS:
        # FILTERS["size_category"] 가 SIZE_CASE 로 라벨 비교를 하므로 라벨로 넘긴다.
        # 정수 2 를 그대로 넘기면 '소형' 과 비교돼 아무것도 안 걸린다.
        profile["size_category"] = SIZE_LABELS[size]

    allergens = query(
        "SELECT al.name_ko FROM pet_allergy AS pa "
        "JOIN allergen AS al ON al.allergen_id = pa.allergen_id WHERE pa.pet_id = ?",
        (pet_id,),
    )
    if allergens:
        profile["allergy"] = [name for (name,) in allergens]
    return profile