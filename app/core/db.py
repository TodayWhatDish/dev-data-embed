"""데이터베이스에 닿는 자리를 여기 하나로 모은다.

다른 파일은 전부 이렇게 쓴다 ─
    from app.core.db import query, one, dicts
"""

import sqlite3
from app.core.config import DB_PATH, INDEX_FILTER
con = sqlite3.connect(DB_PATH)


def query(sql, params=()):
    """여러 줄을 꺼낸다. 튜플의 목록이 온다."""
    return con.execute(sql, params).fetchall()


def one(sql, params=()):
    """한 줄만 꺼낸다. 없으면 None 이 온다."""
    return con.execute(sql, params).fetchone()


def dicts(sql, params=()):
    """컬럼 이름이 붙은 딕셔너리 목록으로 꺼낸다."""
    cur = con.execute(sql, params)
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]

def source_fingerprint(con):
    """색인 대상 데이터의 현재 상태를 숫자 몇 개로 요약한다.

    load_db.py 는 재실행할 때마다 pet_purchases 를 DROP 후 다시 만든다.
    이때 prepare.py / build_index.py 를 다시 돌리지 않으면 chunks 와 chunk_vectors 만
    옛 데이터를 가리킨 채 남는데, 조인은 purchase_id 로 조용히 성립해서
    에러 없이 엉뚱한 리뷰가 검색된다.
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