"""상용 LLM을 부르는 검사 모음. `python -m eval all --with-llm` 로 돌린다.

    DB만 보는 빠른 검사(마스킹, recall@k, 계층 의존, 청킹)는 tests/(pytest)에 있다.
    여기는 그 반대 - 호출마다 토큰이 나가고 몇 초~몇십 초 걸려서 --with-llm 없이는 안 돈다.
"""


class SkipCheck(Exception):
    """검사 자체는 못 돌린다 (의존성이 이 환경에서 깨져 있는 등) - 실패가 아니라 건너뜀."""
