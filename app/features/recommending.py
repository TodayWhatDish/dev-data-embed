# Last Updated : 2026-08-27

"""후보에서 프로필을 받아 LLM이 지정 개수만큼 고르게 하고, 범위를 벗어나면 다시 재시도.
   모델에게 후보 인덱스 범위 밖 응답이 오거나 형식이 꺠지면 그대로 실패 처리하지 않고, 오류를 알려주며 다시 재시도한다.
   products.py가 좁혀준 후보 안에서만 LLM이 고르도록 강제하고, 형식 깨진 응답을 재시도로 잡는 자리. 
"""
from typing import Any

MAX_RETRIES = 2

def recommend(candidates: list[dict[str,Any]], profile: dict[str,Any], n_pick: int = 5) -> tuple[Any, int, str]:
    """후보 중에 n_pick개 만큼 고른 결과와 재시도 횟수, 마지막 오류를 돌려준다."""
    pass

