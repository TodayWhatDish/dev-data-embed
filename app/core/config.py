# Last updated: 2026-08-27
# Last Updated : 2026-08-23

""" 모든 스크립트가 공유하는 설정값과 상수를 모아둔다

    경로, 모델 이름, 토큰 한도, 색깅 대상 조건과 같은 '값' 선언.
    표준 라이브러리 및 경로를 정의.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / 'data'
DB_PATH = DATA_DIR / 'pet_reco.db'
MASTER_DIR = DATA_DIR / 'master'
LOG_PATH = ROOT / 'query_log.jsonl'
SEED_DIR = DATA_DIR / 'seed'

# 다국어 지원 모델(한국어 포함) - 문장을 고정 차원 벡터로 변환
EMBED_MODEL = 'intfloat/multilingual-e5-small'

# 특정 임베딩 모델로 청킹하고 토큰화 했다면 값비교도 무조건 같은 모델로 비교해야함
EMBED_TOKENIZER = "intfloat/multilingual-e5-small"

# 해당 모델의 최대 토큰수가 512인데 전달의 문자정보의 토큰갯수가 넘어설떄 512넘어서는 정보값은 짤려서 누락됨
EMBED_MAX_TOKENS = 512

EMBED_BATCH_SIZE = 32

EMBED_DEVICE = "cpu"

# 코사인 유사도용
EMBED_NORMALIZE = True

# 색인 대상 리뷰를 고르는 조건. review 테이블이 r 로 별칭된 쿼리에서 쓴다.
# is_holdout=1 은 추천 성능 평가용으로 남겨둔 행이라 색인에서 뺀다.
INDEX_FILTER = """
    r.is_holdout = 0
    AND r.body IS NOT NULL
    AND TRIM(r.body) <> ''
"""

if not Path(DB_PATH).exists():
    print(f"알림: DB 가 아직 없다 -> {DB_PATH}")


# .env 를 환경변수로 올린다.
def load_env(path=ROOT / ".env"):
    """.env를 환경변수로 올린다."""
    if not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k,v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k,v)

def env(name: str, default: str) -> str:
    """환경변수를 읽되, 빈 문자열은 기본값으로 친다."""
    value = os.environ.get(name,"").strip()
    return default if value == "" else value

USE_API = env("USE_API",0) == "1"

if USE_API:
    LLM_BASE_URL = "https://api.openai.com/v1"
    LLM_API_KEY = env("OPENAI_API_KEY", "")
    LLM_MODEL = env("API_MODEL", "gpt-4o-mini")
else:
    LLM_BASE_URL = "http://localhost:11434/v1"
    LLM_API_KEY = "ollama"
    LLM_MODEL = "qwen2.5:3b"

