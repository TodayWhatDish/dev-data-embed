# LastUpdated : 2026-08-13
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'pet_reco.db'
DATA_DIR = ROOT / 'data'
LOG_PATH = ROOT / 'query_log.jsonl'
# 다국어 지원 모델(한국어 포함) - 문장을 고정 차원 벡터로 변환
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'