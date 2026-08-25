# Last Updated : 2026-08-23

""" 모든 스크립트가 공유하는 설정값과 상수를 모아둔다

    경로, 모델 이름, 토큰 한도, 색깅 대상 조건과 같은 '값' 선언.
    표준 라이브러리 및 경로를 정의.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / 'data'
DB_PATH = DATA_DIR / 'pet_reco.db'
LOG_PATH = ROOT / 'query_log.jsonl'

# 다국어 지원 모델(한국어 포함) - 문장을 고정 차원 벡터로 변환
EMBED_MODEL = 'intfloat/multilingual-e5-small'

# 특정 임베딩 모델로 청킹하고 토큰화 했다면 값비교도 무조건 같은 모델로 비교해야함
EMBED_TOKENIZER = "intfloat/multilingual-e5-small"

# 해당 모델의 최대 토큰수가 512인데 전달의 문자정보의 토큰갯수가 넘어설떄 512넘어서는 정보값은 짤려서 누락됨
EMBED_MAX_TOKENS = 512

# 색인 대상 리뷰를 고르는 조건. pet_purchases 가 p 로 별칭된 쿼리에서 쓴다.
# is_holdout=1 은 추천 성능 평가용으로 남겨둔 행이라 색인에서 뺀다.
# build_index.py 와 search.py 가 같은 기준을 봐야 재색인 필요 여부를 판단할 수 있어 여기 둔다.
INDEX_FILTER = """
    p.is_holdout = 0
    AND p.review IS NOT NULL
    AND TRIM(p.review) <> ''
"""

CHUNK_SIZE =75
CHUNK_OVERLAP = 48
PREFIX_BUDGET =32 #접두사 [제품명 > 중제목] 본문내용
RESPLIT_OVER = EMBED_MAX_TOKENS-PREFIX_BUDGET
HEADERS = [("##","section")] #청킹할 데이터의 표시 경계 구분점 생성(Markdown)
SEPERATORS = ["\n\n","\n","다","요",".",",",""]

BATCH_SIZE = 32
if not Path(DB_PATH).exists():
    print(f"알림: DB 가 아직 없다 -> {DB_PATH}")