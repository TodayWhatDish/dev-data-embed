# Last Updated: 2026-09-04

"""짧은 자연어 질문으로 검색 후보의 품질과 안전을 잰다.  python -m eval qa_check

golden.py 와 무엇이 다른가. 저기는 홀드아웃 리뷰 '전문'을 질의로 넣어 원래 산 상품이
다시 나오는지(recall@k) 본다. 실제 사용자는 리뷰 전문을 안 친다 - "관절 좋은 사료
있어요?" 한 줄을 친다. 짧은 질의는 신호가 훨씬 적어서 같은 검색기라도 성적이 다르다.
그 차이를 안 재면 배포하고 나서야 안다.

정답을 product_id 하나로 못 박지 않는 이유는 qa_golden.json 의 '만든 법' 에 적어 뒀다.

LLM 을 한 번도 안 부른다 - 요금이 안 든다.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(errors="replace")

from app.features.searching import candidates as search_candidates
from pipeline.vector_db import connect

from eval.tracing import banner, eval_run, warm_domain

GOLDEN = json.loads((Path(__file__).parent / "qa_golden.json").read_text(encoding="utf-8"))
ITEMS = GOLDEN["items"]

K = 5

# expect 의 키 -> 그 속성을 만족하는 product_id 를 뽑는 SQL. 값 하나를 파라미터로 받는다.
# 여기서만 상품 속성을 읽으므로 조건을 늘릴 때 고칠 곳이 한 군데다.
EXPECT_SQL = {
    "feeding_purpose": """
        SELECT pfp.product_id FROM product_feeding_purpose AS pfp
        JOIN feeding_purpose AS fp ON fp.feeding_purpose_id = pfp.feeding_purpose_id
        WHERE fp.name_ko = ?
    """,
    "food_form": "SELECT product_id FROM product WHERE food_form = ?",
    "ingredient": """
        SELECT pi.product_id FROM product_ingredient AS pi
        JOIN ingredient AS ing ON ing.ingredient_id = pi.ingredient_id
        WHERE ing.name_ko = ?
    """,
}

ANIMAL_SQL = """
    SELECT pac.product_id FROM product_animal_category AS pac
    JOIN animal_category AS ac ON ac.animal_category_id = pac.animal_category_id
    WHERE ac.name_ko = ?
"""

ALLERGEN_SQL = """
    SELECT pi.product_id FROM product_ingredient AS pi
    JOIN ingredient_allergen AS ia ON ia.ingredient_id = pi.ingredient_id
    JOIN allergen AS al ON al.allergen_id = ia.allergen_id
    WHERE al.name_ko = ?
"""

# 색인에 실제로 들어간(is_holdout=0) 리뷰가 달린 상품. 리뷰가 없으면 벡터 검색이
# 그 상품을 애초에 못 돌려주므로, 자가검증은 '상품이 있나' 가 아니라 여기까지 봐야 한다.
INDEXED_SQL = """
    SELECT DISTINCT pu.product_id
    FROM purchase AS pu
    JOIN chunks AS c ON c.purchase_id = pu.purchase_id
"""


def ids(con: sqlite3.Connection, sql: str, params: tuple = ()) -> set[int]:
    """SQL 한 방을 product_id 집합으로 바꾼다. 집합 연산으로 조건을 겹치려고 쓴다."""
    return {row[0] for row in con.execute(sql, params)}


def expected_products(con: sqlite3.Connection, item: dict) -> set[int]:
    """이 문항에서 '맞다'고 칠 상품 집합. expect 조건을 전부 만족하고 축종도 맞아야 한다."""
    matched = ids(con, ANIMAL_SQL, (item["profile"]["animal_category"],))
    for key, value in item["expect"].items():
        matched &= ids(con, EXPECT_SQL[key], (value,))

    # 알레르기를 준 문항은 그 알레르겐이 든 상품을 정답에서 뺀다 - 조건은 맞아도
    # 줘서는 안 되는 상품이라 '맞은 것'으로 세면 안 된다.
    allergy = item["profile"].get("allergy")
    if allergy:
        matched -= ids(con, ALLERGEN_SQL, (allergy,))
    return matched


def self_check(con: sqlite3.Connection) -> list[tuple]:
    """채점을 시작하기 전에 자가 성한지 본다.

    expect 를 만족하면서 색인된 리뷰까지 있는 상품이 없으면 그 문항은 아무리 검색이
    잘해도 0점이다. 그건 검색이 나쁜 게 아니라 자가 틀린 것이다.
    """
    indexed = ids(con, INDEXED_SQL)
    broken = []
    for item in ITEMS:
        for key in item["expect"]:
            if key not in EXPECT_SQL:
                broken.append((item["id"], f"모르는 expect 키: {key}"))
        reachable = expected_products(con, item) & indexed
        if not reachable:
            broken.append((item["id"], "조건을 만족하면서 색인된 리뷰가 있는 상품이 없다"))
    return broken


def score_item(con: sqlite3.Connection, item: dict) -> dict:
    """문항 하나를 실제 배포 경로(searching.candidates)로 검색해 채점한다."""
    profile = item["profile"]
    found = search_candidates(profile, item["question"], limit=K)
    got = [row["product_id"] for row in found]

    wanted = expected_products(con, item)
    animal_ok = ids(con, ANIMAL_SQL, (profile["animal_category"],))
    allergy = profile.get("allergy")
    unsafe = ids(con, ALLERGEN_SQL, (allergy,)) if allergy else set()

    return {
        "id": item["id"],
        "question": item["question"],
        "n": len(got),
        "hit": any(pid in wanted for pid in got),
        "n_match": sum(1 for pid in got if pid in wanted),
        "n_wrong_animal": sum(1 for pid in got if pid not in animal_ok),
        "n_unsafe": sum(1 for pid in got if pid in unsafe),
        "has_allergy": bool(allergy),
        "got": got,
    }


def main() -> int:
    banner("짧은 질문으로 검색이 조건에 맞는 후보를 가져오나 (qa_check)")
    warm_domain()

    con = connect()
    try:
        with eval_run("qa_check", inputs={"문항": len(ITEMS), "k": K}) as run:
            print("=" * 74)
            print("1. 골든셋이 데이터와 맞나 (자가검증)")
            print("=" * 74)

            broken = self_check(con)
            print(f"  문항 {len(ITEMS)}개 · 어긋난 것 {len(broken)}개")
            for qid, reason in broken:
                print(f"      {qid}번: {reason}")
            if broken:
                print("\n  자가 틀렸다. 채점은 여기서 멈춘다 - 틀린 자로 잰 숫자는 없느니만 못하다.")
                run.record(골든셋_어긋남=len(broken))
                return 1
            print("  전부 DB 로 확인됐다. 이제 이걸 자로 쓸 수 있다")

            print()
            print("=" * 74)
            print(f"2. 후보 상위 {K}개가 조건을 만족하나")
            print("=" * 74)

            rows = [score_item(con, item) for item in ITEMS]
            n = len(rows)
            n_returned = sum(r["n"] for r in rows)

            hit = sum(r["hit"] for r in rows) / n * 100
            precision = sum(r["n_match"] for r in rows) / n_returned * 100 if n_returned else 0.0
            wrong_animal = sum(r["n_wrong_animal"] for r in rows)

            print(f"  hit@{K} {hit:.0f}%  ·  precision@{K} {precision:.0f}%   ({n}문항 · 후보 {n_returned}건)")
            print(f"  축종이 어긋난 후보 {wrong_animal}/{n_returned}건")
            print()
            print("  hit@k 는 '상위 k 에 맞는 게 하나라도 있나', precision@k 는 '몇 개나 맞나'다.")
            print("  화면에 5개를 보여준다면 사용자가 체감하는 건 precision 쪽이다.")

            print()
            print("=" * 74)
            print("3. 알레르기 필터가 지켜지나 (안전)")
            print("=" * 74)

            allergy_rows = [r for r in rows if r["has_allergy"]]
            unsafe = sum(r["n_unsafe"] for r in allergy_rows)
            allergy_returned = sum(r["n"] for r in allergy_rows)
            print(f"  알레르기를 준 {len(allergy_rows)}문항 · 후보 {allergy_returned}건 중 위반 {unsafe}건")
            print("  여기는 0 이 아니면 무조건 버그다. 품질 지표가 아니라 안전 지표다.")
            for r in allergy_rows:
                if r["n_unsafe"]:
                    print(f"      {r['id']}번: {r['question']}  -> 위반 {r['n_unsafe']}건 {r['got']}")

            run.record(**{
                f"hit@{K}": round(hit, 1),
                f"precision@{K}": round(precision, 1),
                "축종_어긋남": wrong_animal,
                "알레르기_위반": unsafe,
                "후보_건수": n_returned,
            })

            misses = [r for r in rows if not r["hit"]]
            if misses:
                print()
                print(f"  못 맞힌 문항 {len(misses)}개. 왜 못 맞혔는지를 본다:")
                for r in misses:
                    print(f"      {r['id']}. {r['question']}")
                    print(f"          받은 후보 {r['got']}")

            return 1 if unsafe else 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
