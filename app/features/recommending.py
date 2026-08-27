# Last Updated : 2026-08-27

""" products.py가 좁혀준 후보 안에서만 LLM이 고르도록 강제하고, 형식 깨진 응답을 재시도로 잡는 자리.
    이 검증이 없으면 LLM이 후보에 없는 상품을 지어내도 그대로 나감.
"""
from typing import Any

MAX_RETRIES = 2

def recommend(candidates: list[dict[str,Any]], profile: dict[str,Any], n_pick: int = 5) -> tuple[Any, int, str]:
    """후보 중에 n_pick개 만큼 고른 결과와 재시도 횟수, 마지막 오류를 돌려준다."""
    pass

