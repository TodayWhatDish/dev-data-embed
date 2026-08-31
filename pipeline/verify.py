"""
전체 흐름 요약

  1. 테이블의 데이터 개수와 연결 상태를 검사한다.
  2. 벡터를 불러와 차원과 모델 이름을 검사한다.
  3. 벡터의 현재 저장 크기와 BLOB 예상 크기를 계산한다.
  4. 임베딩 토큰 상한을 넘는 문서 조각이 있는지 검사한다.
  5. 세 가지 추천 방식의 hit@1·3·5 결과를 비교한다.
  6. 예시 질문으로 실제 검색 결과를 확인한다.

  verify.py는 검사 순서와 입력값을 보여 주고,
  verifying.py는 각 검사를 실제로 수행한다.
"""

import sqlite3
import sqlite_vec
from app.core.config import DB_PATH, EMBED_DIM, EMBED_MAX_TOKENS, EMBED_MODEL
from pipeline.prep import verifying

con = sqlite3.connect(DB_PATH)  # DB연결통로 만듬
con.enable_load_extension(True)
sqlite_vec.load(con)            # 6단계 vec_distance_cosine 계산에 필요
con.enable_load_extension(False)

problems = []  # 문제들을 모아놓을 예정

# 검사할 테이블 이름. 지금 DB에 실제로 있는 7개.
TABLE_NAMES = (
    "pet_customers", "pet_products", "pet_profiles", "pet_purchases",
    "chunks", "chunk_vectors", "embedding_meta",
)

# 벡터 종류와 각 벡터 테이블의 ID 컬럼 이름.
# product_vectors/customer_vectors는 pipeline/prep_rec.py를 먼저 돌려야 생긴다.
KINDS = (
    ("chunk_vectors", "purchase_id"),
    ("product_vectors", "product_id"),
    ("customer_vectors", "customer_id"),
)

#===========   1. 테이블의 데이터 개수와 연결 상태를 검사한다. ====================================>

verifying.check_table_data(con, TABLE_NAMES, problems)

#===========   2. 벡터를 불러와 차원과 모델 이름을 검사한다. ====================================>

vectors = verifying.check_vector_data(con, KINDS, EMBED_DIM, EMBED_MODEL, problems)

#===========   3. 벡터의 현재 저장 크기와 BLOB 예상 크기를 계산한다. ====================================>

vec_vol = con.execute(f"""
    SELECT COUNT(*), (length(vector)), SUM(length(vector))
    FROM {KINDS[0][0]}""").fetchone()

print(f" ㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡ")
print(f" 총 {vec_vol[0]}개, 벡터 하나당{vec_vol[1]/1024:.2f}KB, 전체 벡터{vec_vol[2]/1024:.2f}KB")
print(f" ㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡ")
# 1KB = 1024바이트 .. 그래서 / 1024를 하였습니다

#===========   4. 임베딩 토큰 상한을 넘는 문서 조각이 있는지 검사한다. ====================================>

token_result = verifying.check_token_sizes(con, EMBED_MAX_TOKENS, problems)

#===========   5. 세 가지 추천 방식의 hit@1·3·5 결과를 비교한다. ====================================>

# pipeline/prep_rec.py를 먼저 돌려야 홀드아웃/product_vectors/customer_vectors가 채워진다.
hit_results = verifying.compare_recommendations(con, vectors, token_result)

#===========   6. 예시 질문으로 실제 검색 결과를 확인한다. ====================================>

verifying.search_any(con, "chunk", ["환불하고 싶은데 어떻게 하나요?"])

# 조각이 아닌 다른 자료를 근거로 찾고 싶으면 search_any()에 종류 이름만 넘긴다.
# verifying.search_any(con, "product", ["건성 피부에 좋은 수분 크림"])

#===========   여섯 단계에서 발견한 문제를 모아 최종 출력한다. ====================================>

verifying.print_final_result(problems)
con.close()
