# Last Updated : 2026-08-27

"""상품CRUD, 프로필 조건으로 상품 후보를 골라 dict 리스트로 돌려주는 필터 층.
   같은 트랜잭션 흐름 안에서 한 건만 다시 임베딩한다.
   이 파일이 없으면 LLM에 상품 전체를 넘기게 돼서 토큰 낭비 + 축종/알러지 안 맞는 후보까지 섞여 들어감
"""
from typing import Any

def candidates(profiles: dict[str, Any], limit: int=20) -> list[dict[str, Any]]:
    """프로필에 맞는 상품 후보를 반환한다. (스키마 확정 전까지 pass)"""
    pass


