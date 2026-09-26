# Last Updated: 2026-09-25

"""벡터 색인/검색 쿼리에 끼워 쓰는 SQL 조각."""

from app.core.config import SIZE_LABELS

# 색인 대상 리뷰를 고르는 조건. review 테이블이 r 로 별칭된 쿼리에서 쓴다.
# is_holdout=1 은 추천 성능 평가용으로 남겨둔 행이라 색인에서 뺀다.
INDEX_FILTER = """
    r.is_holdout = 0
    AND r.body IS NOT NULL
    AND TRIM(r.body) <> ''
"""

# SIZE_LABELS(config.py) 표로 SQL CASE 를 만든다 - 표를 두 군데 적으면 반드시 어긋난다.
SIZE_CASE = (
    "CASE pu.size_at_purchase "
    + " ".join(f"WHEN {code} THEN '{label}'" for code, label in SIZE_LABELS.items())
    + " END"
)
