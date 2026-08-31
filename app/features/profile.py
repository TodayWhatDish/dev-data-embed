# Last Updated : 2026-08-27

""" 사용자 입력(자유 형식)을 products.candidates()와 recommending.recommend() 
    둘 다 받는 dict 형태로 통일하는 자리. 
    안 두면 입력 파싱을 두 함수가 각자 다르게 하게 됨.
"""

from typing import Any
from app.domain.common import CommonMgr

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
    """자유 형식 입력을 products.candidates()/recommending.recommend()가 공통으로 쓰는 dict로 통일한다."""
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