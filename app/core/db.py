"""데이터베이스에 닿는 자리를 여기 하나로 모은다.

다른 파일은 전부 이렇게 쓴다 ─
    from app.core.db import query, one, dicts
"""

import sqlite3
import json
from app.core.config import DB_PATH, INDEX_FILTER

con = sqlite3.connect(DB_PATH)


def query(sql, params=()) -> list[tuple]:
    """여러 줄을 꺼낸다. 튜플의 목록이 온다."""
    return con.execute(sql, params).fetchall()


def one(sql, params=()) -> tuple | None:
    """한 줄만 꺼낸다. 없으면 None 이 온다."""
    return con.execute(sql, params).fetchone()


def dicts(sql, params=()) -> list[dict]:
    """컬럼 이름이 붙은 딕셔너리 목록으로 꺼낸다."""
    cur = con.execute(sql, params)
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]

# 문자로 넣어둔 백터정보를 Numpy 행렬로 숫자화해서 되살리는 함수
def load_vectors(table, key, connection=None):
    import numpy as np

    # 만약 해당 함수를 호출하는 파일에 con접속객체가 있으면 그걸 재활용하고 없으면 새로 만들어서 전달
    active_con = connection if connection is not None else con

    # DB에 가지고온 id값과 벡터 좌표값을 담을 빈 리스트 2개 생성
    ids, rows = [], []

    # 인수로 전달된 테이블에서 ID열과 vector 열을 한 행씩 가져옴
    for row_id, vector in active_con.execute(f"SELECT {key}, vector FROM {table}"):
        ids.append(row_id)
        # 리스트에 따옴표가 붙어있어서 통짜로 문자화되어 있는 데이터를 json객체형태로 변경
        rows.append(json.loads(vector))

    # 객체안쪽에 있는 vector안쪽의 좌표값을 다시 숫자형태로 변경
    return ids, np.array(rows, dtype="float32")


def source_fingerprint(con) -> str:
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
    return ":".join(str(v) for v in row)
