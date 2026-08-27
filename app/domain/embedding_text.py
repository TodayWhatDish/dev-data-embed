# Last Updated : 2026-08-27

""" 상품 dict 한 건을 임베딩용 문장 하나로 바꾸는 순수 함수 모음
    앱과 파이프라인이 같이 쓴다. 앱이 pipeline/ 를 import 할 수 없다.
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


