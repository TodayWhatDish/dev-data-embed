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
LOG_PATH = ROOT / 'logs' / 'query_log.jsonl'
SEED_DIR = DATA_DIR / 'seed'

LOGGER_DIR = ROOT / 'log'

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

# 모델마다 다른 값을 한 표에 모은다. 접두사를 코드 여러 곳에 적으면 반드시 어긋난다.
# query_prefix/passage_prefix: e5 계열은 필수, bge 계열은 붙이면 오히려 성능이 떨어진다.
# 모델을 비교할 때 이 표만 늘리고 코드는 건드리지 않는 것이 목표다.
EMBED_PROFILES = {
    'intfloat/multilingual-e5-small': {
        'dim': 384, 'max_tokens': 512, 'batch_size': 32,
        'query_prefix': 'query: ', 'passage_prefix': 'passage: ',
    },
    'intfloat/multilingual-e5-base': {
        'dim': 768, 'max_tokens': 512, 'batch_size': 16,
        'query_prefix': 'query: ', 'passage_prefix': 'passage: ',
    },
    'BAAI/bge-m3': {
        'dim': 1024, 'max_tokens': 8192, 'batch_size': 8,
        'query_prefix': '', 'passage_prefix': '',
    },
}

# 재색인 없이 실험하려면 셸에서 바꾼다:  $env:EMBED_MODEL = 'BAAI/bge-m3'
EMBED_MODEL = env('EMBED_MODEL', 'intfloat/multilingual-e5-small')

if EMBED_MODEL not in EMBED_PROFILES:
    raise SystemExit(f"EMBED_PROFILES 에 없는 모델입니다: {EMBED_MODEL}")

_profile = EMBED_PROFILES[EMBED_MODEL]

# 토큰화는 임베딩과 반드시 같은 모델이어야 한다 - 따로 적을 이유가 없어 파생값으로 둔다.
EMBED_TOKENIZER = EMBED_MODEL
EMBED_DIM = _profile['dim']
EMBED_MAX_TOKENS = _profile['max_tokens']
EMBED_BATCH_SIZE = _profile['batch_size']
QUERY_PREFIX = _profile['query_prefix']
PASSAGE_PREFIX = _profile['passage_prefix']

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

# 체급 코드(1~5) -> 사람이 쓰는 말. SQL 과 파이썬이 같은 표를 봐야 하므로 여기 하나만 둔다.
SIZE_LABELS = {1: '초소형', 2: '소형', 3: '중형', 4: '대형', 5: '초대형'}

# 위 표에서 SQL CASE 를 만들어 쓴다 - 표를 두 군데 적으면 반드시 어긋난다.
SIZE_CASE = "CASE pu.size_at_purchase " + " ".join(
    f"WHEN {code} THEN '{label}'" for code, label in SIZE_LABELS.items()
) + " END"


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

load_env()
USE_API = env("USE_API",0) == "1"

if USE_API:
    LLM_BASE_URL = "https://api.openai.com/v1"
    LLM_API_KEY = env("OPENAI_API_KEY", "")
    LLM_MODEL = env("API_MODEL", "gpt-4o-mini")
else:
    LLM_BASE_URL = "http://localhost:11434/v1"
    LLM_API_KEY = "ollama"
    LLM_MODEL = "qwen2.5:3b"

# CHOI 추가함. 구글 로그인이랑 서버 세션 토큰 만드는 데 필요한 설정값 4개를 미리 꺼내놓음.
# 이 값들 없으면 나중에 구글 로그인 기능 자체가 동작을 못 함.
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", "")
JWT_SECRET = env("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # 7일
ADMIN_PASSWORD = env("ADMIN_PASSWORD", "")

SUPABASE_URL = env("SUPABASE_URL", "") # CHOI 추가
SUPABASE_KEY = env("SUPABASE_KEY", "") # CHOI 추가
