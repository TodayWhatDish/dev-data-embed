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

    # dict 형태가 아닌 자료형(tuple)이라면, dict 형태로 만든다.
    data = row if isinstance(row, Mapping) else dict(zip(PRODUCT_FIELDS, row))
    parts = [str(data[field]) for field in PRODUCT_FIELDS if data.get(field)] # 행에 있는 정보를 문자열 리스트로 저장한다
    return "passage:\n" + " ".join(parts)


def source_hash(text: str) -> str:
    """문장의 지문. 같은 문장이면 같은 값 → 재임베딩 스킵 판단에 씀."""
    pass


