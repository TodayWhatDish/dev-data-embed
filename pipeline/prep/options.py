# Last updated: 2026-08-27
# Last Updated : 2026-08-26

"""조각을 어떻게 자를지 정하는 값들

"""

from app.core.config import EMBED_MAX_TOKENS

CHUNK_SIZE =75
CHUNK_OVERLAP = 48
PREFIX_BUDGET =32 #접두사 [제품명 > 중제목] 본문내용
RESPLIT_OVER = EMBED_MAX_TOKENS-PREFIX_BUDGET
HEADERS = [("##","section")] #청킹할 데이터의 표시 경계 구분점 생성(Markdown)
SEPARATORS = ["\n\n","\n","다","요",".",",",""]
