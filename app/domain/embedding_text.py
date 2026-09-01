# Last Updated : 2026-08-30

"""
    쿼리 -> {**여기부터 DB와 관련 없이 동작하는 로직**} -> 상품 rows -> 상품 row -> 문장 변환 로직
    파이프라인(색인 만들 때)과 app(실시간 후보 문장 만들 때) 둘 다 공용 로직 작성
"""

import hashlib
from typing import Any,Mapping
from app.core.config import PASSAGE_PREFIX

PRODUCT_FIELDS = (
    "brand", "product_name", "category", "sub_category",
    "target_animal_category", "target_feeding_purpose", "target_food_form",
    "ingredients", "tags", "description",
)

def product_text(row: Mapping[str, Any] | tuple) -> str:
    """
    상품 한 건(dict/tuple)을 검색용 문장 하나로 만든다.
    row: Mapping[str, Any] | tuple => `dict 형태 또는 tuple 형태로 인자가 들어온다.`
    """

    # dict 형태가 아닌 자료형(tuple)이라면, dict 형태로 만든다.
    data = row if isinstance(row, Mapping) else dict(zip(PRODUCT_FIELDS, row))
    parts = [str(data[field]) for field in PRODUCT_FIELDS if data.get(field)] # 행에 있는 정보를 문자열 리스트로 저장한다
    return PASSAGE_PREFIX + " ".join(parts)



def source_hash(text: str) -> str:
    """문장의 지문. 같은 문장이면 같은 값 → 재임베딩 스킵 판단에 씀."""
    return hashlib.sha256(text.encode()).hexdigest()


def _group(pairs, name_of):
    """(product_id, 마스터 id) 목록을 {product_id: [이름...]} 으로 묶는다.

    1:N 관계 테이블을 조인하지 않고 전량 스캔해 오기 때문에 여기서 묶는다.
    이름은 마스터 캐시(name_of)에서 찍는다 - 관계 테이블 조회에 조인이 없다.
    """
    grouped = {}
    for product_id, master_id in pairs:
        grouped.setdefault(product_id, []).append(name_of(master_id))
    return grouped


def build_product_rows(products, animal_category_ids, feeding_purpose_ids, ingredient_ids,
                       *, animal_category_name, feeding_purpose_name, ingredient_name,
                       category_of):
    """상품 행 + 관계 3종을 product_text() 가 받는 행 목록으로 조립한다.

    DB 에 닿지 않는다. 재료는 repositories 가 읽어오고, 이름은 마스터 캐시가 준다.
    * products: product 행 목록(dict)
    * *_ids: (product_id, 마스터 id) 튜플 목록
    * *_name: 마스터 id -> 이름 함수
    * category_of: product_category_id -> (대분류, 소분류) 함수

    수치(가격/중량/영양)는 넣지 않는다. 임베딩이 숫자로 의미를 만들지 못하고,
    그 조건은 프로필 선필터(SQL)가 거른다 (CLAUDE.md 도메인 규칙 4).
    """
    animals = _group(animal_category_ids, animal_category_name)
    purposes = _group(feeding_purpose_ids, feeding_purpose_name)
    ingredients = _group(ingredient_ids, ingredient_name)

    rows = []
    for product in products:
        product_id = product["product_id"]
        category, sub_category = category_of(product["product_category_id"])
        rows.append({
            "product_id": product_id,
            "brand": product["brand"],
            "product_name": product["name"],
            "category": category,
            "sub_category": sub_category,
            # 축종이 비면 그 상품은 아무에게도 안 뜬다(fail-closed). 문장에도 그대로 비워 둔다.
            "target_animal_category": ", ".join(animals.get(product_id, [])),
            "target_feeding_purpose": ", ".join(purposes.get(product_id, [])),
            "target_food_form": product["food_form"],
            "ingredients": ", ".join(ingredients.get(product_id, [])),
            "tags": None,
            "description": product["description"],
        })
    return rows
