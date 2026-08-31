# Last updated: 2026-08-27
# LastUpdated : 2026-08-26

"""chunk_vectors를 기반으로 유사리뷰를 찾는 행위를한다. (검색)
   
   프로필 키를 기준으로 조각 점수를 반환하며, 사용자 쿼리 호출시 사용된다.
"""

import sqlite3

from app.core.config import EMBED_MODEL,SIZE_CASE

# 프로필 키 -> SQL 조건절. 값이 들어온 키만 WHERE 에 붙는다.
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
    params 로 바인딩하므로 사용자 입력을 SQL 문자열에 이어붙이지 않는다.
    """
    clauses, params = [f"r.rating >= {MIN_RATING}"], []
    for key, clause in FILTERS.items():
        value = profile.get(key)
        if not value:
            continue
        # 알레르기처럼 값이 여러 개면 같은 조건절을 값마다 반복해 AND 로 묶는다.
        # 하나만 걸면 나머지 알레르겐이 든 상품이 그대로 통과한다.
        for item in (value if isinstance(value, list) else [value]):
            clauses.append(clause)
            params.append(item)

    return " AND ".join(clauses) or "1=1", tuple(params)


def check_freshness(con: sqlite3.Connection):
    """색인 시점의 모델,데이터 지문을 지금 DB와 비교해 어긋난 점을 문장 목록으로 돌려준다. 맞으면 빈 목록.

    load_csv.py 재실행 후 재색인을 잊으면 chunk_vectors 만 옛 데이터를 가리키는데,
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
        problems.append("embed.py 를 다시 실행하세요.")
    return problems


