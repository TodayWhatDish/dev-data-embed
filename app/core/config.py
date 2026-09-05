# Last updated: 2026-09-03
# Last Updated: 2026-09-03

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
# 모델별 평가 결과를 남긴다. 모델을 바꿔 재색인하면 이전 결과는 DB에서 사라지므로
# 비교하려면 DB 밖에 남겨둬야 한다.
EVAL_DIR = DATA_DIR / 'eval'

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


# 아래 설정값이 전부 env() 를 거치므로 .env 는 그것들보다 먼저 올라와야 한다.
# 정의만 해두고 부르지 않으면 .env 전체가 조용히 무시된다 - 값이 안 읽혀도
# 에러가 안 나고 기본값으로 굴러가기 때문에 알아채기 어렵다.

load_env()

# query_prefix/passage_prefix: e5 계열은 필수, bge 계열은 붙이면 오히려 성능이 떨어진다.
# 모델을 비교할 때 이 표만 늘리고 코드는 건드리지 않는 것이 목표다.
#
# provider: 벡터를 누가 만드는지. 'st' 는 로컬 sentence-transformers, 'openai' 는 API 호출이다.
#   OpenAI 모델은 가중치를 내려받을 수 없어 SentenceTransformer/AutoTokenizer 로는 못 올린다.
#   그래서 '표에 못 넣는' 게 아니라, 표에 provider 칸을 하나 늘려서 embedder/chunking 이
#   그 칸만 보고 갈라지게 했다 - 모델을 늘리는 자리는 여전히 이 표 하나뿐이다.
# tokenizer: 토큰을 세는 쪽. HF 모델은 자기 이름(모델=토크나이저)이고,
#   OpenAI 모델은 tiktoken 인코딩 이름을 적는다.
EMBED_PROFILES = {
    'intfloat/multilingual-e5-small': {
        'provider': 'st', 'tokenizer': 'intfloat/multilingual-e5-small',
        'dim': 384, 'max_tokens': 512, 'batch_size': 32,
        'query_prefix': 'query: ', 'passage_prefix': 'passage: ',
    },
    'intfloat/multilingual-e5-base': {
        'provider': 'st', 'tokenizer': 'intfloat/multilingual-e5-base',
        'dim': 768, 'max_tokens': 512, 'batch_size': 16,
        'query_prefix': 'query: ', 'passage_prefix': 'passage: ',
    },
    'BAAI/bge-m3': {
        'provider': 'st', 'tokenizer': 'BAAI/bge-m3',
        'dim': 1024, 'max_tokens': 8192, 'batch_size': 8,
        'query_prefix': '', 'passage_prefix': '',
    },
    # batch_size 는 GPU 메모리가 아니라 한 번의 HTTP 요청에 몇 개를 실을지다.
    # API 한도는 요청당 입력 2048개지만, 하나 실패하면 그 묶음을 통째로 다시 보내야 하므로 128로 둔다.
    'text-embedding-3-small': {
        'provider': 'openai', 'tokenizer': 'cl100k_base',
        'dim': 1536, 'max_tokens': 8191, 'batch_size': 128,
        'query_prefix': '', 'passage_prefix': '',
    },
}

# 재색인 없이 실험하려면 셸에서 바꾼다:  $env:EMBED_MODEL = 'BAAI/bge-m3'
# EMBED_MODEL = env('EMBED_MODEL', 'intfloat/multilingual-e5-small')
EMBED_MODEL = env('EMBED_MODEL', 'intfloat/multilingual-e5-small')

if EMBED_MODEL not in EMBED_PROFILES:
    raise SystemExit(f"EMBED_PROFILES 에 없는 모델입니다: {EMBED_MODEL}")

_profile = EMBED_PROFILES[EMBED_MODEL]

# 토큰화는 임베딩과 반드시 같은 모델이어야 한다 - HF 모델은 모델 이름이 그대로 토크나이저 이름이고,
# OpenAI 모델만 tiktoken 인코딩 이름이 따로 있어 프로파일에서 읽는다.
EMBED_PROVIDER = _profile['provider']
EMBED_TOKENIZER = _profile['tokenizer']
EMBED_DIM = _profile['dim']
EMBED_MAX_TOKENS = _profile['max_tokens']
EMBED_BATCH_SIZE = _profile['batch_size']
QUERY_PREFIX = _profile['query_prefix']
PASSAGE_PREFIX = _profile['passage_prefix']

# provider='st' 일 때만 쓴다. API 모델은 남의 서버에서 도니 올릴 장치가 없다.
EMBED_DEVICE = "cpu"

# provider='openai' 인 프로파일에서만 필요하다. LLM 키(LLM_API_KEY)와 갈라 둔 이유:
# 채팅 모델은 Anthropic 을 쓰면서 임베딩만 OpenAI 로 돌리는 조합이 흔하다.
EMBED_API_KEY = env("EMBED_API_KEY", env("OPENAI_API_KEY", ""))

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


USE_API = env("USE_API",0) == "1"

# LLM_PROVIDER는 langchain init_chat_model()의 provider 인자로 그대로 들어간다 (adapters/stores/llm.py).
# 상용 API를 바꾸고 싶으면 .env의 LLM_PROVIDER/LLM_API_KEY/API_MODEL 세 값만 바꾸면 된다 - 코드 수정 불필요.
if USE_API:
    LLM_PROVIDER = env("LLM_PROVIDER", "anthropic")
    LLM_BASE_URL = None  # provider 네이티브 클라이언트는 base_url이 필요 없다 (OpenAI 호환 프록시를 쓸 때만 .env로 지정)
    LLM_API_KEY = env("LLM_API_KEY", "")
    LLM_MODEL = env("API_MODEL", "claude-sonnet-5")
    # 답변을 만든 모델이 자기 답을 채점하면 관대해지는 self-evaluation bias가 있다 -
    # 반증(verify)은 이 모델을 대신 쓴다 (참고: https://mjforge.tistory.com/30).
    VERIFY_MODEL = env("VERIFY_MODEL", "claude-haiku-4-5-20251001")
else:
    LLM_PROVIDER = "openai"  # Ollama가 OpenAI 호환 엔드포인트를 흉내내므로 provider는 openai로 두고 base_url만 로컬로 돌린다
    LLM_BASE_URL = "http://localhost:11434/v1"
    LLM_API_KEY = "ollama"
    LLM_MODEL = "qwen2.5:3b"
    VERIFY_MODEL = LLM_MODEL  # ponytail: 로컬은 모델 하나뿐이라 분리 안 함 - Ollama에 두 번째 모델 받으면 나눌 것

# 채점(eval/*)을 LangSmith 로도 보낼지. 꺼져 있어도 채점은 그대로 돌고 data/eval/runs.jsonl 에는 남는다.
# 채점용 프로젝트를 서비스 로그와 가르는 이유: 채점은 같은 질문 수십 개를 몰아 던져서,
# 실제 요청과 같은 통에 부으면 평균 응답시간 같은 서비스 지표가 채점 때문에 망가진다.
LANGSMITH_TRACING = env("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_EVAL_PROJECT = env("LANGSMITH_EVAL_PROJECT", "pet-reco-eval")

# 관리자 로그인 / 서버 세션 토큰 만드는 데 필요한 설정값.
# 관리자 로그인 전용 JWT 설정. 사용자 인증은 Supabase 로 이관 중이라 구글 로그인과
# 함께 걷어냈지만, 관리자 인증(features/admin_auth.py)은 공용 비밀번호 + 자체 JWT 라
# 그 이관과 무관하다. core/auth.py 와 features/admin_auth.py 가 이 세 값을 import 한다.
JWT_SECRET = env("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # 7일
ADMIN_PASSWORD = env("ADMIN_PASSWORD", "")

# 고객 페이지 배경 이미지용 (app/api/routes/background.py)
UNSPLASH_ACCESS_KEY = env("UNSPLASH_ACCESS_KEY", "")
