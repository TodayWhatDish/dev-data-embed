# Last Updated: 2026-09-23

"""chunk_vectors를 기반으로 유사리뷰를 찾는 행위를한다. (검색)

프로필 키를 기준으로 조각 점수를 반환하며, 사용자 쿼리 호출시 사용된다.

DB 에는 repositories/embedding.py 를 통해서만 닿는다. services 에 SQL 이 있으면
스키마가 바뀔 때 고칠 곳이 두 층으로 흩어진다.

FILTERS 의 조건절은 SQL 조각이지만 여기 남는다. 실행하는 게 아니라 벡터 검색에
넘길 WHERE 를 조립하는 것이고, 무엇으로 거를지는 검색 정책이라 services 의 일이다.

벡터 거리는 pgvector의 `<=>`(코사인 거리) 연산자를 쓴다 - 예전 sqlite-vec 의
vec_distance_cosine()과 값은 같고 이름만 다르다.
"""

import logging

from sqlalchemy import text

from app.core.config import EMBED_DIM, EMBED_MODEL, SIZE_CASE
from app.core.embedder import embed_query

logger = logging.getLogger()


# 프로필 키 -> SQL 조건절. 값이 들어온 키만 WHERE 에 붙는다. 자리표시자는 build_where()가
# :p0, :p1 ... 로 채운다(포지션 하나당 ? 하나 - SQLAlchemy text()는 이름 바인딩만 받는다).
# size_at_purchase 는 1~5 코드라 SIZE_CASE(config.py)로 사람이 쓰는 말로 바꿔 비교한다.
# 알러지는 pet_allergy 가 다대다라 EXISTS 로 "그 알러지가 등록돼 있는가"를 확인한다.
FILTERS = {
    "size_category": f"""
        {SIZE_CASE} = ?
    """,
    # 사용자가 "소고기 알레르기"라고 입력하면, 이건 "소고기 알레르기 있는 개가 쓴 리뷰는 빼자"일 뿐 — 그 상품에 소고기가 들어있는지는 전혀 안 보기에 수정
    # pet_allergy(리뷰어의 알레르기) 기준 → product_ingredient+ingredient_allergen(상품 원료의 알레르겐) 기준
    "allergy": """
        NOT EXISTS (
            SELECT 1 FROM product_ingredient AS pi
            JOIN ingredient_allergen AS ia ON ia.ingredient_id = pi.ingredient_id
            JOIN allergen AS al ON al.allergen_id = ia.allergen_id
            WHERE pi.product_id = pu.product_id AND al.name_ko = ?
        )
    """,
    "animal_category": """
        EXISTS (
            SELECT 1 FROM pet AS pe
            JOIN animal_category AS ac ON ac.animal_category_id = pe.animal_category_id
            WHERE pe.pet_id = pu.pet_id AND ac.name_ko = ?
        )
    """,
}


def fmt_purchase_id(pid: int):
    """정수 purchase_id 를 사람이 읽기 쉬운 원래 표기로 되돌린다. 418 -> 'O00418'

    저장은 INTEGER로 하되(조인/인덱스에 유리) 화면에 찍을 때만 접두어를 붙인다.
    검색 결과에 ID만 덩그러니 나오면 어느 테이블 것인지 알아보기 어렵기 때문이다.
    """
    return f"O{pid:05d}"


MIN_RATING = 3


def build_where(profile):
    """프로필 딕셔너리를 WHERE 절과 바인딩 파라미터로 바꾼다.

    값이 있는 키만 조건절로 만들고, 아무것도 없으면 '1=1'(조건 없음)을 돌려준다.
    바인딩하므로 사용자 입력을 SQL 문자열에 이어붙이지 않는다. FILTERS 의 ? 는 등장
    순서대로 :p0, :p1 ... 로 바뀐다 - search() 가 같은 순서로 params 를 딕셔너리에 얹는다.
    """
    clauses, params = [f"r.rating >= {MIN_RATING}"], []
    unknown = profile.keys() - FILTERS.keys()
    if unknown:
        # 오타난 프로필 키는 조건이 통째로 안 걸리는데 에러도 안 난다 - 결과가 넓어질 뿐이라 조용하다
        logger.warning(f"프로필에 모르는 키 {sorted(unknown)} - 해당 조건은 안 걸린다")

    for key, clause in FILTERS.items():
        value = profile.get(key)
        if not value:
            continue
        # 알레르기처럼 값이 여러 개면 같은 조건절을 값마다 반복해 AND 로 묶는다.
        # 하나만 걸면 나머지 알레르겐이 든 상품이 그대로 통과한다.
        for item in value if isinstance(value, list) else [value]:
            clauses.append(clause.replace("?", f":p{len(params)}"))
            params.append(item)

    logger.debug(f"WHERE 조립: 조건 {len(clauses)}개, params={tuple(params)}")
    return " AND ".join(clauses) or "1=1", tuple(params)


def chunk_fingerprint(con) -> str:
    """지금 chunks 테이블의 지문. embed.py 가 색인 때 남기는 것과 같은 식으로 계산한다."""
    n, id_sum, token_sum = con.execute(
        text("SELECT COUNT(*), COALESCE(SUM(purchase_id), 0), COALESCE(SUM(n_tokens), 0) FROM chunks")
    ).one()
    return f"{n}:{id_sum}:{token_sum}"


def check_freshness(con):
    """색인 시점의 모델,데이터 지문을 지금 DB와 비교해 어긋난 점을 문장 목록으로 돌려준다. 맞으면 빈 목록.

    load_csv.py 재실행 후 재색인을 잊으면 chunk_vectors 만 옛 데이터를 가리키는데,
    조인이 purchase_id 로 조용히 성립해 에러 없이 엉뚱한 리뷰가 나온다. 알리기만 하고 막지는 않는다.
    """
    meta = dict(con.execute(text("SELECT key, value FROM embedding_meta")).all())
    problems = []

    if meta.get("model") != EMBED_MODEL:
        problems.append(
            f"색인은 '{meta.get('model')}' 모델로 만들었는데 지금 설정은 '{EMBED_MODEL}' 입니다. "
            "벡터 공간이 달라 유사도가 의미를 잃습니다."
        )

    if meta.get("dim") != str(EMBED_DIM):
        problems.append(f"색인 벡터는 {meta.get('dim')}차원인데 지금 모델은 {EMBED_DIM}차원입니다.")

    # embed.py 가 색인 시점에 남긴 조각 지문을 지금 chunks 로 다시 계산해 대조한다.
    # chunk.py 만 돌리고 embed.py 를 잊는 게 재색인 사이클에서 가장 흔한 실수다.
    now = chunk_fingerprint(con)
    if meta.get("source") != now:
        problems.append(f"색인 당시 조각 지문은 '{meta.get('source')}' 인데 지금 chunks 는 '{now}' 입니다.")

    if problems:
        problems.append("chunk.py 와 embed.py 를 다시 실행하세요.")
        # 부르는 쪽이 문장만 출력하고 넘어가므로, 로그에도 남겨야 나중에 되짚을 수 있다
        for line in problems:
            logger.warning(f"색인 신선도: {line}")
    else:
        logger.debug("색인 신선도 확인 - 모델/차원/조각 지문 모두 일치")

    return problems


def search(con, query, where="1=1", params: tuple = (), top_k: int = 3):
    """입력된 자연어 질문 하나를 받아서, DB에 저장된 리뷰 조각들 중 질문과 의미가 가장 비슷한 것을 최대 top_k개 뽑아준다.
    질문 -> 벡터 -> DB안 벡터들과 거리 비교 -> 정렬 -> 중복 제거 -> 최종 까지의 프로세스를 거친다."""

    for line in check_freshness(con):
        print(f"[경고] {line}")

    # embed_query()가 QUERY_PREFIX와 정규화를 다 챙긴다 - 모델이 로컬이든 API든 여기는 안 바뀐다.
    # pgvector는 문자열 리터럴 "[v1,v2,...]"을 :: vector 로 캐스팅해서 받는다.
    q_vec = "[" + ",".join(map(str, embed_query(query))) + "]"

    bind = {f"p{i}": v for i, v in enumerate(params)}
    bind["qvec"] = q_vec

    # rows는 chunk 하나 당 한줄을 의미한다.
    rows = con.execute(
        text(f"""
        SELECT v.purchase_id, pu.product_id, c.body,
               v.vector <=> CAST(:qvec AS vector) AS distance
        FROM chunk_vectors AS v
        JOIN chunks AS c ON c.purchase_id = v.purchase_id AND c.chunk_index = v.chunk_index
        JOIN purchase AS pu ON pu.purchase_id = v.purchase_id
        JOIN review AS r ON r.purchase_id = pu.purchase_id
        WHERE {where}
        ORDER BY distance
    """),
        bind,
    ).all()

    # 구매건마다 사용자 검색어랑 가장 비슷한 조각 하나만 남긴다(중복 제거).
    best = {}
    for purchase_id, product_id, body, distance in rows:
        if purchase_id not in best or distance < best[purchase_id][2]:
            best[purchase_id] = (product_id, body, distance)

    # 상품이 겹치면 제일 유사도 높은 리뷰 하나만 남긴다 - 후보 3개가 같은 상품 리뷰로 채워지는 것을 방지 (중복제거)
    best_per_product = {}
    for purchase_id, (product_id, body, distance) in best.items():
        if product_id not in best_per_product or distance < best_per_product[product_id][-1]:
            best_per_product[product_id] = (purchase_id, body, distance)

    ranked = sorted(best_per_product.values(), key=lambda item: item[-1])[:top_k]
    # 1 - 코사인거리 = 유사도. 유사도 높은 순으로 top_k개.
    return [(purchase_id, 1 - distance, body) for purchase_id, body, distance in ranked]
