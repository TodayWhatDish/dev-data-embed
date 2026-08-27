# Last Updated : 2026-08-27

""" 상품 dict → 문장 변환 로직. 
    파이프라인(색인 만들 때)과 app(실시간 후보 문장 만들 때) 둘 다 이 규칙이 필요해서 — 안 두면 같은 변환 로직을 두 곳에 따로 짜야 함.
"""

import hashlib
from typing import Any,Mapping

PRODUCT_FIELDS = ()

def product_text(row: Mapping[str, Any] | tuple) -> str:
    """상품 한 건(dict)을 검색용 문장 하나로 만든다. 어떤 키가 오든 있는 값만 이어붙인다."""
    pass

def source_hash(text: str) -> str:
    """문장의 지문. 같은 문장이면 같은 값 → 재임베딩 스킵 판단에 씀."""
    pass


