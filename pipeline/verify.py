"""점검. 파이프라인이 만든 것이 쓸 수 있는 물건인지 확인한다.

  1. 개수     표마다 몇 행인가. 벡터가 빠진 행은 없는가
  2. 벡터     차원 · 모델 · 정규화가 맞는가
  3. 저장     BLOB 실제 크기가 예상과 맞는가
  4. 토큰     상한을 넘어 잘리는 것은 없는가
  5. 합치기   한 상품의 조각 점수를 max 로 합칠까 mean 으로 합칠까
  6. 눈으로   실제 질문을 던져 본다

이 파일은 순서만 정한다. 재는 일과 눈으로 보는 검색은 전부 prep/verifying.py 에 있다
(참고파일은 checks.py/metrics.py/inspect.py 로 나뉘어 있지만, 우리는 검사·점수 로직을
verifying.py 하나에 몰아뒀고 눈으로 보는 검색(inspect.py)만 따로 뺐다).

아무것도 만들지 않는다. 몇 번을 돌려도 데이터가 안 바뀐다.
여기서 문제가 하나라도 나오면 앱을 붙이기 전에 고친다.

앞:    python -m pipeline.embed
실행:  python -m pipeline.verify
"""

import sqlite3

from app.core.config import DB_PATH, EMBED_DIM, EMBED_MAX_TOKENS, EMBED_MODEL
from pipeline.prep import verifying
from pipeline.prep.inspect import inspect

con = sqlite3.connect(DB_PATH)
problems = []

# 검사할 테이블 이름. 지금 DB에 실제로 있는 8개.
TABLE_NAMES = (
    "user", "product", "pet", "purchase", "review",
    "chunks", "chunk_vectors", "embedding_meta",
)

# 벡터 세 벌과 각 표의 열쇠 컬럼. 여기서 한 줄을 빠뜨리면 점검이 두 벌만 보고
# 이상 없다고 말한다. 검사가 조용히 거짓말을 하는 자리다.
# product_vectors/customer_vectors는 pipeline/prep_rec.py를 먼저 돌려야 생긴다.
KINDS = (
    ("chunk_vectors", "purchase_id"),
    ("product_vectors", "product_id"),
    ("customer_vectors", "customer_id"),
)


def banner(title):
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


banner("1. 개수")
verifying.check_table_data(con, TABLE_NAMES, problems)
# check_copied_values는 여기 없다 - 참고파일의 chunk_vectors는 상품명 등을 미리
# 복사해 두는 비정규화 표라 그 사본이 원본과 같은지 재는 검사였는데, 우리
# chunk_vectors(purchase_id, chunk_index, vector)는 그런 사본 자체를 안 가진다.

banner("2. 벡터")
vectors = verifying.check_vector_data(con, KINDS, EMBED_DIM, EMBED_MODEL, problems)

banner("3. 저장 방식")
verifying.check_vector_storage(con, KINDS, vectors, EMBED_DIM, problems)

banner("4. 토큰")
token_result = verifying.check_token_sizes(con, EMBED_MAX_TOKENS, problems)

banner("5. 한 상품의 조각 점수를 어떻게 합치나 (max vs mean)")
# pipeline/prep_rec.py를 먼저 돌려야 홀드아웃/product_vectors/customer_vectors가 채워진다.
hit_results = verifying.compare_recommendations(con, vectors, token_result)

banner("6. 눈으로. 세 벌 다 던져 본다")
# review_vectors는 우리한테 없어서(리뷰는 chunk 단위로만 저장) chunk/product/customer 세 벌만 본다.
inspect(con, "chunk", ["배송은 얼마나 걸리나요", "환불하고 싶은데 어떻게 하나요"])
inspect(con, "product", ["건성 피부에 좋은 수분 크림"], top_k=2)
inspect(con, "customer", ["민감성 피부인 사람"], top_k=2)

# 이 데이터의 급소를 확인한다. 참고파일 데이터는 '환불' 이 한 번도 안 나오고
# '교환·반품' 으로만 적혀 있었는데, 우리 데이터는 어떤지 직접 세어본다.
print()
for word in ("환불", "반품", "교환"):
    n = con.execute("SELECT COUNT(*) FROM chunks WHERE body LIKE ?",
                    (f"%{word}%",)).fetchone()[0]
    print(f"  '{word}' 이 들어간 조각: {n:,}개")
print(f"  지금 임베딩은 {EMBED_MODEL} 이다. 어느 낱말을 쓰든 벡터 검색만 믿으면 안 된다.")

verifying.print_final_result(problems)
con.close()
