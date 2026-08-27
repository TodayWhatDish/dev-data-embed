# LastUpdated : 2026-08-26

"""chunk_vectors를 기반으로 유사리뷰를 찾는 행위를한다. (검색)
   
   프로필 키를 기준으로 조각 점수를 반환하며, 사용자 쿼리 호출시 사용된다.
"""
import json
import sqlite3
import numpy as np

from collections import defaultdict
from sentence_transformers import SentenceTransformer
from app.core.config import EMBED_MODEL
from app.core.embedder import get_embeddings

# 프로필 키 -> SQL 조건절. 값이 들어온 키만 WHERE 에 붙는다.
FILTERS = {
    "size_category": "p.size_category = ?",
    "allergy": "(p.allergy IS NULL OR p.allergy <> ?)",
}


def fmt_purchase_id(pid: int):
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


def check_freshness(con: sqlite3.Connection):
    """색인 시점의 모델,데이터 지문을 지금 DB와 비교해 어긋난 점을 문장 목록으로 돌려준다. 맞으면 빈 목록.

    load_db.py 재실행 후 재색인을 잊으면 chunk_vectors 만 옛 데이터를 가리키는데,
    조인이 purchase_id 로 조용히 성립해 에러 없이 엉뚱한 리뷰가 나온다. 알리기만 하고 막지는 않는다.
    """
    meta = dict(con.execute("SELECT key, value FROM embedding_meta").fetchall())
    problems = []

    if meta.get("model") != EMBED_MODEL:
        problems.append(
            f"색인은 '{meta.get('model')}' 모델로 만들었는데 지금 설정은 '{EMBED_MODEL}' 입니다. "
            "벡터 공간이 달라 유사도가 의미를 잃습니다."
        )
   
    if problems:
        problems.append("embed_reviews.py 를 다시 실행하세요.")
    return problems

class VectorStore:
    """chunk_vectors 를 chunks 와 조인해 한 번만 읽어 메모리에 들고 있는 검색기.

    SQLite에는 벡터 타입이 없어서 build_index.py 가 JSON 문자열로 저장한다.
    질의할 때마다 다시 읽으면 4000여 조각 x 384차원의 JSON을 매번 파싱하게 되는데
    대화형 루프에서는 이 비용이 질문 수만큼 반복된다.
    그래서 생성 시 전부 올려두고, 이후 질의에서는 WHERE 로 걸러진 purchase_id 만
    받아 그 리뷰에서 나온 조각 행들을 골라 쓴다.

    한 행은 리뷰가 아니라 조각 하나다. 리뷰 하나가 여러 행을 차지한다.

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

        # 벡터와 본문이 다른 테이블에 있어 조인해서 읽는다. chunk_vectors 는
        # (purchase_id, chunk_index) 와 벡터만 들고, 보여줄 본문은 chunks 쪽에 있다.
        rows = con.execute("""
            SELECT v.purchase_id, k.body, v.vector
            FROM chunk_vectors AS v
            JOIN chunks AS k
              ON k.purchase_id = v.purchase_id
             AND k.chunk_index = v.chunk_index
            ORDER BY v.purchase_id, v.chunk_index
        """).fetchall()
        if not rows:
            raise SystemExit(
                "chunk_vectors 가 비어 있습니다. prepare.py 와 build_index.py 를 차례로 실행하세요."
            )

        self.purchase_ids = [r[0] for r in rows]
        self.docs = [r[1] for r in rows]
        self.matrix = np.array([json.loads(r[2]) for r in rows], dtype=np.float32)

        # purchase_id -> 그 리뷰에서 나온 조각들의 행 번호 '목록'.
        # 예전 {pid: i} 는 리뷰당 벡터가 하나일 때만 맞았다. 지금은 리뷰 1439건이
        # 조각 4172개로 쪼개져 있어서, 같은 pid 가 여러 번 나오면 마지막 값이
        # 앞선 조각을 덮어써 그 조각들이 조용히 사라진다.
        self.rows_of = defaultdict(list)
        for i, pid in enumerate(self.purchase_ids):
            self.rows_of[pid].append(i)

    def search(self, query, where="1=1", params=(), top_k=3):
        """프로필 조건으로 리뷰를 먼저 줄이고, 그 조각들 중 최고 점수로 리뷰 순위를 매긴다.

        벡터 유사도만으로는 "소형견", "닭고기 알레르기 없음" 같은 조건이 지켜지지 않는다.
        (의미가 비슷하기만 하면 대형견 리뷰도 상위에 올라온다.)
        실제 추천 API도 이 순서(프로필 필터 -> 벡터 랭킹)를 따라야 한다.

        돌려주는 top_k 는 '조각 k개'가 아니라 '리뷰 k건'이다. 한 리뷰의 조각들은
        내용이 겹쳐서 나란히 상위에 오르기 쉬운데, 그대로 자르면 top_k=3 요청에
        서로 다른 리뷰가 아니라 같은 리뷰의 조각 3개가 돌아온다.
        """
        # 예전에는 여기서 벡터 테이블을 조인했지만 이제 조인하지 않는다.
        # 조인하면 리뷰 한 건이 조각 수만큼 중복으로 나오고, 색인 대상인지 여부는
        # 아래 rows_of 에 그 id 가 있는지로 이미 걸러진다.
        picked = self.con.execute(
            f"""
            SELECT p.purchase_id
            FROM pet_purchases AS p
            WHERE {where}
        """,
            params,
        ).fetchall()

        # 리뷰 id -> 조각 행 번호로 펼친다. 색인 이후 pet_purchases 가 바뀌었을 수
        # 있으므로 캐시에 있는 id 만 남는다. (defaultdict 에 빈 목록을 새로 심지
        # 않으려고 [] 대신 get 으로 읽는다.)
        idx = [row for (pid,) in picked for row in self.rows_of.get(pid, ())]
        if not idx:
            return []

        # 저장할 때 정규화했으므로 내적만으로 코사인 유사도가 된다.
        # 질의 한 건마다 진행 바가 뜨면 대화형 출력이 지저분해져서 끈다.
        q = self.model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )[0]
        scores = self.matrix[idx] @ q

        # 조각 점수를 리뷰 단위로 접는다. 평균이 아니라 최댓값을 쓴다.
        # 조각들은 CHUNK_OVERLAP 만큼 겹쳐 있어 평균은 서로를 희석시키고,
        # "이 리뷰의 어느 한 대목이 질문과 맞는다"가 우리가 찾는 신호이기 때문이다.
        best = {}
        for pos, row in enumerate(idx):
            pid = self.purchase_ids[row]
            score = float(scores[pos])
            if pid not in best or score > best[pid][0]:
                # 점수와 함께 그 점수를 낸 조각의 본문을 들고 있는다.
                best[pid] = (score, self.docs[row])

        # 리뷰로 접은 뒤에 자른다. 이제 top_k 개는 서로 다른 리뷰다.
        ranked = sorted(best.items(), key=lambda item: -item[1][0])[:top_k]
        return [(pid, score, doc) for pid, (score, doc) in ranked]
