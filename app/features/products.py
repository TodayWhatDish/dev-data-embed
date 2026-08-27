# Last Updated : 2026-08-27

""" 정형 필터(SQL)가 먼저 거르고 LLM은 그 후보 위에서만 판단"을 실행하는 자리. 
    이게 없으면 LLM에 상품 전체를 넘기게 돼서 토큰 낭비 + 축종/알러지 안 맞는 후보까지 섞여 들어감.
"""
from typing import Any

def candidates(profiles: dict[str, Any], limit: int=20) -> list[dict[str, Any]]:
    """프로필에 맞는 상품 후보를 반환한다. (스키마 확정 전까지 pass)"""
    pass


