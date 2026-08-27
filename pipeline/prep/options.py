# Last Updated : 2026-08-26

"""조각을 어떻게 자를지 정하는 값들

"""

from app.core.config import EMBED_MAX_TOKENS

CHUNK_SIZE = 384            # 조각 하나의 토큰 상한
CHUNK_OVERLAP = 48          # 경계에서 겹치는 몫
PREFIX_BUDGET = 32          # 접두어("[상품명 > 섹션]")가 쓸 토큰 자리

# 계산해서 잡는다. 상한이 바뀌면 문턱도 따라 움직인다 ― 손으로 두 번 적으면 한쪽만 고치게 된다
RESPLIT_OVER = EMBED_MAX_TOKENS - PREFIX_BUDGET

HEADERS = [("##", "section")]

SEPARATORS = ["\n\n", "\n", "다. ", "요. ", ". ", " ", ""]