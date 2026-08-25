# LastUpdated : 2026-08-25

# review_vectors 에 저장된 벡터로 유사 리뷰를 찾는 검색 모듈
#
# 색인(build_index.py)과 파일을 나눈 이유는 두 작업의 수명이 다르기 때문이다.
# 색인은 데이터가 바뀔 때만 한 번 돌리면 되고(1400여 건 인코딩에 십수 초),
# 검색은 그 결과를 읽기만 한다. 한 파일에 두면 검색만 확인하고 싶을 때도
# 임베딩을 통째로 다시 만들게 된다.
import json
import sqlite3
from sentence_transformers import SentenceTransformer
import numpy as np
from app.core.embedder import get_embeddings
from app.core.config import EMBED_MODEL
from app.core.db import source_fingerprint
from collections import defaultdict

# 프로필 키 -> SQL 조건절. 값이 들어온 키만 WHERE 에 붙는다.
FILTERS = {
    "size_category": "p.size_category = ?",
    "allergy": "(p.allergy IS NULL OR p.allergy <> ?)",
}


def fmt_purchase_id(pid):
    """정수 purchase_id 를 사람이 읽기 쉬운 원래 표기로 되돌린다. 418 -> 'O00418'

    저장은 INTEGER로 하되(조인/인덱스에 유리) 화면에 찍을 때만 접두어를 붙인다.
    검색 결과에 ID만 덩그러니 나오면 어느 테이블 것인지 알아보기 어렵기 때문이다.
    """
    return f"O{pid:05d}"


def build_where(profile):
    """프로필 딕셔너리를 WHERE 절과 바인딩 파라미터로 바꾼다.

    값이 있는 키만 조건절로 만들고, 아무것도 없으면 '1=1'(조건 없음)을 돌려준다.
    params 로 바인딩하므로 사용자 입력을 SQL 문자열에 이어붙이지 않는다.
    """
    clauses, params = [], []
    for key, clause in FILTERS.items():
        if profile.get(key):
            clauses.append(clause)
            params.append(profile[key])

    return " AND ".join(clauses) or "1=1", tuple(params)


def check_freshness(con):
    """review_vectors 가 지금 DB 상태와 맞는지 확인하고, 어긋난 점을 문장으로 돌려준다.

    load_db.py 를 다시 돌리면 pet_purchases 가 통째로 새로 만들어지는데,
    이때 build_index.py 를 잊으면 review_vectors 만 옛 데이터를 가리킨 채 남는다.
    조인은 purchase_id 로 조용히 성립하므로 에러 없이 엉뚱한 리뷰가 검색된다.
    막을 방법이 없으니 최소한 눈에 띄게 알린다.

    검색을 막지는 않는다. 색인이 조금 낡아도 확인용으로는 여전히 쓸 만하고,
    여기서 SystemExit 를 내면 데이터를 만지는 중에 아무것도 못 하게 되기 때문이다.
    """
    meta = dict(con.execute("SELECT key, value FROM embedding_meta").fetchall())
    problems = []

    if meta.get("model") != EMBED_MODEL:
        problems.append(
            f"색인은 '{meta.get('model')}' 모델로 만들었는데 지금 설정은 '{EMBED_MODEL}' 입니다. "
            "벡터 공간이 달라 유사도가 의미를 잃습니다."
        )

    # 'source' 키는 이 검사를 넣기 전에 만든 색인에는 없다. 그때는 판단을 보류한다.
    indexed = meta.get("source")
    if indexed is not None and indexed != source_fingerprint(con):
        problems.append(
            f"색인 이후 pet_purchases 가 바뀌었습니다 (색인 시점 {indexed} -> 현재 {source_fingerprint(con)})."
        )

    if problems:
        problems.append("build_index.py 를 다시 실행하세요.")
    return problems


class VectorStore:
    """review_vectors 를 한 번만 읽어 메모리에 들고 있는 검색기.

    SQLite에는 벡터 타입이 없어서 build_index.py 가 JSON 문자열로 저장한다.
    질의할 때마다 다시 읽으면 1400여 건 x 384차원, 즉 10MB가 넘는 JSON을
    매번 파싱하게 되는데 대화형 루프에서는 이 비용이 질문 수만큼 반복된다.
    그래서 생성 시 전부 올려두고, 이후 질의에서는 WHERE 로 걸러진 purchase_id 만
    받아 해당 행을 골라 쓴다.

    벡터가 통째로 메모리에 올라가므로 색인이 커지면(수십만 건) 이 방식 대신
    FAISS 같은 벡터 인덱스로 옮겨야 한다.
    """

    def __init__(
        self, con: sqlite3.Connection, model: SentenceTransformer | None = None
    ):
        self.con = con
        self.model = model or get_embeddings()

        self.warnings = check_freshness(con)
        for line in self.warnings:
            print(f"[경고] {line}")

        rows = con.execute("""
            SELECT purchase_id, doc, vector
            FROM review_vectors
            ORDER BY purchase_id
        """).fetchall()
        if not rows:
            raise SystemExit(
                "review_vectors 가 비어 있습니다. 먼저 build_index.py 를 실행하세요."
            )

        self.ids = [r[0] for r in rows]
        self.docs = [r[1] for r in rows]
        self.matrix = np.array([json.loads(r[2]) for r in rows], dtype=np.float32)
        # purchase_id -> matrix 행 번호. WHERE 결과를 행 번호로 바꿀 때 쓴다.
        self.row_of = {pid: i for i, pid in enumerate(self.ids)}

    def search(self, query, where="1=1", params=(), top_k=3):
        """프로필 조건으로 후보를 먼저 줄인 뒤, 남은 후보만 유사도로 정렬한다.

        벡터 유사도만으로는 "소형견", "닭고기 알레르기 없음" 같은 조건이 지켜지지 않는다.
        (의미가 비슷하기만 하면 대형견 리뷰도 상위에 올라온다.)
        실제 추천 API도 이 순서(프로필 필터 -> 벡터 랭킹)를 따라야 한다.
        """
        picked = self.con.execute(
            f"""
            SELECT v.purchase_id
            FROM review_vectors AS v
            JOIN pet_purchases AS p ON p.purchase_id = v.purchase_id
            WHERE {where}
        """,
            params,
        ).fetchall()

        # 색인 이후 pet_purchases 가 바뀌었을 수 있으므로 캐시에 있는 id 만 남긴다
        idx = [self.row_of[r[0]] for r in picked if r[0] in self.row_of]
        if not idx:
            return []

        # 저장할 때 정규화했으므로 내적만으로 코사인 유사도가 된다.
        # 질의 한 건마다 진행 바가 뜨면 대화형 출력이 지저분해져서 끈다.
        q = self.model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )[0]
        scores = self.matrix[idx] @ q
        return [
            (self.ids[idx[i]], float(scores[i]), self.docs[idx[i]])
            for i in np.argsort(-scores)[:top_k]
        ]

'''
class VectorStore:
    def __init__(self, con: sqlite3.Connection, model: SentenceTransformer | None = None):
        """chunk_vectors를 chunks 와 JOIN해서 한 번만 읽어 메모리에 들고 있는 검색기."""
        self.con = con
        self.model = model
        self.warnings = check_freshness(con)
        for line in self.warnings:
            print(f"[경고] {line}")

        # TODO: chunk_vectors + chunks JOIN해서 purchase_id, chunk_index, body, vector 읽기
        # TODO: self.purchase_ids, self.docs, self.matrix 채우기
        # TODO: self.rows_of = defaultdict(list) 로 purchase_id -> 행번호 목록 만들기
        pass

    def search(self,query: str, where: str = "1=1", params: tuple = (), top_k:int = 3) -> list[tuple[int,float,str]]:
        """프로필 조건으로 구매 건을 먼저 줄이고, 그 조각들 중 최고 점수로 구매 건을 순위 매긴다."""
        # TODO: pet_purchases 에서 프로필 조건(where)에 맞는 purchase_id 목록(picked) 조회
        # TODO: picked -> self.rows_of 로 조각 행번호(idx) 펼치기
        # TODO: 빈 idx면 [] 리턴
        # TODO: 질의 벡터 만들고 idx 행들과 내적(scores) 계산
        # TODO: purchase_id 단위로 최고 점수 조각만 남기기 (best딕셔너리)
        # TODO: 점수 내림차순 top_k개 잘라서 (purchase_id, score, doc) 튜플 목록으로 리턴
        pass
'''
