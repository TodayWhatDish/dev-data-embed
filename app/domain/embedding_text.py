# Last Updated : 2026-08-30

"""
    쿼리 -> {**여기부터 DB와 관련 없이 동작하는 로직**} -> 상품 rows -> 상품 row -> 문장 변환 로직
    파이프라인(색인 만들 때)과 app(실시간 후보 문장 만들 때) 둘 다 공용 로직 작성
"""

import hashlib
from typing import Any,Mapping

PRODUCT_FIELDS = (
    "brand", "product_name", "category", "sub_category",
    "target_feeding_purpose", "target_food_form",
    "ingredients", "tags", "description",
)

def product_text(row: Mapping[str, Any] | tuple) -> str:
    """
    상품 한 건(dict/tuple)을 검색용 문장 하나로 만든다.
    row: Mapping[str, Any] | tuple => `dict 형태 또는 tuple 형태로 인자가 들어온다.`
    """

    # dict 형태로 들어온다면 tuple 형태로 바꾼다
    if isinstance(row, Mapping):
        row = tuple(row[field] for field in PRODUCT_FIELDS)


    # ==== wip =====
    # brand, name, category, sub_category, purpose, food_form, ingredients, tags, _description = row

    # # category(상위 분류)가 없는 상품(예: '사료'처럼 그 자체가 최상위)은
    # # sub_category만 쓴다 - 안 그러면 "None/사료"처럼 리터럴 None이 문서에 박힌다.
    # category_text = f"{category}/{sub_category}" if category else sub_category
    # tags_text = f" 태그: {tags}" if tags else ""

    # return (
    #     "passage: "
    #     f"{brand} {name} "
    #     f"({category_text}, {food_form}) "
    #     f"{purpose} 목적 "
    #     f"주원료: {ingredients}"
    #     f"{tags_text}"
    # )


def source_hash(text: str) -> str:
    """문장의 지문. 같은 문장이면 같은 값 → 재임베딩 스킵 판단에 씀."""
    return hashlib.sha256(text.encode()).hexdigest()


