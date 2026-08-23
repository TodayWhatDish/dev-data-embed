# LastUpdated : 2026-08-17
# 모든 스크립트가 공유하는 설정과 규칙. 표준 라이브러리만 쓰므로
# 데이터만 적재하는 경로(load_db.py)는 torch 없이도 돌아간다.
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'pet_reco.db'
DATA_DIR = ROOT / 'data'
LOG_PATH = ROOT / 'query_log.jsonl'
# 다국어 지원 모델(한국어 포함) - 문장을 고정 차원 벡터로 변환
EMBED_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'
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



if not Path(DB_PATH).exists():
    print(f"알림: DB 가 아직 없다 -> {DB_PATH}")

def source_fingerprint(con):
    """색인 대상 데이터의 현재 상태를 숫자 몇 개로 요약한다.

    load_db.py 는 재실행할 때마다 pet_purchases 를 DROP 후 다시 만든다.
    이때 build_index.py 를 다시 돌리지 않으면 review_vectors 만 옛 데이터를 가리킨 채
    남는데, 조인은 purchase_id 로 조용히 성립해서 에러 없이 엉뚱한 리뷰가 검색된다.
    색인 시점의 지문을 embedding_meta 에 남겨두고 검색 시작 시 비교해 이 상황을 잡아낸다.

    건수 / ID 합 / 리뷰 길이 합을 함께 보므로 행 추가·삭제, ID 변경, 본문 수정을 잡는다.
    (길이가 같은 오타 수정처럼 지문이 그대로인 변경은 놓친다. 값싼 안전망이지 검증은 아니다.)
    """
    row = con.execute(f"""
        SELECT COUNT(*),
               COALESCE(SUM(p.purchase_id), 0),
               COALESCE(SUM(LENGTH(p.review)), 0)
        FROM pet_purchases AS p
        WHERE {INDEX_FILTER}
    """).fetchone()
    return ':'.join(str(v) for v in row)