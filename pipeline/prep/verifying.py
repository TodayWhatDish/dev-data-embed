# Last Updated : 2026-08-30

"""
파이프라인 결과를 실제로 검사하는 함수들을 모아둔다.

검증 방법을 담당하며, @verify.py는 필요한 값을 준비하고 이 함수들을 순서대로 호출한다.
"""

import json
import sqlite3
from collections import defaultdict

import numpy as np
from numpy.typing import NDArray


def check(ok: bool, error_msg: str, problems: list[str]):
    """검사 방법은 알지 못하고, 들어오는 조건에 대한 참/거짓만을 판단."""
    if not ok:
        problems.append(error_msg)
    return ok


def check_table_data(con: sqlite3.Connection, table_names: tuple, problems: list[str]):
    """테이블이 실제로 존재하고 비어있지 않은지 검사한다. (1단계)"""
    existing = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    ok_count = 0
    for name in table_names:
        if not check(name in existing, f"{name} 테이블이 없습니다.", problems):
            continue
        count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        if check(count > 0, f"{name} 테이블이 비어있습니다.", problems):
            ok_count += 1
    print(f"[1단계] 테이블 {ok_count}/{len(table_names)}개 정상")


def check_vector_data(con: sqlite3.Connection, kinds: tuple, expected_dim: int, expected_model: str, problems: list[str]):
    """embedding_meta가 설정값과 맞는지 확인하고, 벡터를 실제로 읽어 저장 형식·차원을 검사한다. (2단계)

    저장 형식(BLOB vs JSON 문자열)을 가리지 않고 읽되, retrieve.py/db.load_vectors가
    기대하는 형식과 실제 저장 형식이 다르면 problems에 그 사실 자체를 기록한다.
    """
    meta = dict(con.execute("SELECT key, value FROM embedding_meta"))
    check(meta.get("model") == expected_model,
          f"모델 불일치: 저장값 '{meta.get('model')}', 설정값 '{expected_model}'", problems)
    check(meta.get("dim") == str(expected_dim),
          f"차원 불일치: 저장값 {meta.get('dim')}, 설정값 {expected_dim}", problems)

    vectors = {}
    for table, id_col in kinds:
        rows = con.execute(f"SELECT {id_col}, vector FROM {table}").fetchall()
        if not check(bool(rows), f"{table}에 벡터가 없습니다.", problems):
            continue

        # retrieve.py / db.load_vectors는 chunk_vectors만 읽고 JSON 문자열을 기대한다.
        # product_vectors, customer_vectors는 아직 그 두 파일이 손대지 않는 새 테이블이라
        # BLOB이어도 문제가 아니다 — 그래서 이 검사는 chunk_vectors에만 건다.
        if table == "chunk_vectors":
            sample_type = con.execute(f"SELECT typeof(vector) FROM {table} LIMIT 1").fetchone()[0]
            if sample_type == "blob":
                check(False,
                      f"{table}.vector가 BLOB으로 저장돼 있습니다. "
                      "app/core/db.load_vectors와 app/features/retrieve.py는 JSON 문자열을 기대해 "
                      "json.loads()에서 UnicodeDecodeError로 죽습니다 (검색 기능 실사용 불가 상태).",
                      problems)

        ids, mat = [], []
        for row_id, vec in rows:
            arr = np.frombuffer(vec, dtype=np.float32) if isinstance(vec, bytes) \
                else np.array(json.loads(vec), dtype=np.float32)
            ids.append(row_id)
            mat.append(arr)
        mat = np.array(mat, dtype=np.float32)

        check(mat.shape[1] == expected_dim,
              f"{table} 실제 차원 {mat.shape[1]}, 설정값 {expected_dim}과 다름", problems)
        vectors[table] = (ids, mat)

    print(f"[2단계] 모델={meta.get('model')}, 차원={meta.get('dim')}")
    return vectors


def check_vector_storage(con: sqlite3.Connection, kinds: tuple, vectors: dict, embed_dim: int):
    """[3단계] BLOB 실제 바이트 수와 float32 예상 바이트(dim*4)를 비교한다.

    verify.py가 이미 인라인 SQL로 처리해 여기서는 구현하지 않는다.
    """
    pass


def check_token_sizes(con: sqlite3.Connection, max_tokens: int, problems: list[str]):
    """chunks.n_tokens가 임베딩 모델의 토큰 상한을 넘는 조각이 있는지 검사한다. (4단계)"""
    total = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    over = con.execute(
        "SELECT COUNT(*) FROM chunks WHERE n_tokens > ?", (max_tokens,)
    ).fetchone()[0]
    check(over == 0, f"{max_tokens}토큰 넘는 조각 {over}개 있음", problems)
    print(f"[4단계] 총 {total}개 조각 중 {max_tokens}토큰 초과 {over}개")
    return {"total": total, "over_limit": over}


def calculate_scores(
    customer_vectors: NDArray[np.float32],      # (n_customers, dim)
    product_vectors: NDArray[np.float32],       # (n_products, dim)
    chunk_vectors: NDArray[np.float32],         # (n_chunks, dim)
    chunk_ids: list[int],                       # 조각 하나하나가 속한 purchase_id 목록 (product_of 키용)
    product_ids: list[str],                     # 상품 ID 리스트 (순서 = product_vectors 행 순서)
    product_of: dict[int, str],                 # purchase_id -> product_id 매핑
) -> dict[str, NDArray[np.float32]]:            # 3가지 점수 행렬 (n_customers, n_products)
    """상품요약/조각최고점/조각평균 3방식으로 (고객 x 상품) 점수 행렬을 만든다. (5단계)

    세 벡터가 전부 정규화돼 있으므로(normalize_embeddings=True) 내적 = 코사인 유사도다.
    """
    product_index = {pid: i for i, pid in enumerate(product_ids)}
    n_customers = customer_vectors.shape[0]
    n_products = len(product_ids)

    summary_scores = customer_vectors @ product_vectors.T

    chunk_scores = customer_vectors @ chunk_vectors.T  # (n_customers, n_chunks)
    chunk_max = np.full((n_customers, n_products), -1.0, dtype=np.float32)
    chunk_sum = np.zeros((n_customers, n_products), dtype=np.float32)
    chunk_count = np.zeros(n_products, dtype=np.float32)

    for j, purchase_id in enumerate(chunk_ids):
        product_id = product_of.get(purchase_id)
        p = product_index.get(product_id)
        if p is None:
            continue
        col = chunk_scores[:, j]
        chunk_max[:, p] = np.maximum(chunk_max[:, p], col)
        chunk_sum[:, p] += col
        chunk_count[p] += 1

    chunk_count[chunk_count == 0] = 1  # 0으로 나누기 방지, 해당 상품 열은 평균이 0으로 남는다
    chunk_avg = chunk_sum / chunk_count

    return {
        "상품요약": summary_scores,
        "조각최고점": chunk_max,
        "조각평균": chunk_avg,
    }


def hit_at(
    scores: NDArray[np.float32],                # (n_customers, n_products)
    customer_ids: list[str],                    # 고객 ID 리스트 (scores 행 순서)
    product_ids: list[str],                     # 상품 ID 리스트 (scores 열 순서)
    bought: dict[str, set[str]],                # customer_id -> 이미 산 상품들 집합
    answers: dict[str, str],                    # customer_id -> 정답 상품 (holdout)
    ks: tuple[int, ...] = (1, 3, 5),
) -> dict[int, float]:                          # {k: hit_rate_percent}
    """점수 행렬에서 고객별 정답 상품이 상위 k 안에 들었는지로 hit@k를 계산한다. (5단계)"""
    product_index = {pid: i for i, pid in enumerate(product_ids)}
    max_k = max(ks)
    hits = {k: 0 for k in ks}
    evaluated = 0

    for i, customer_id in enumerate(customer_ids):
        answer = answers.get(customer_id)
        if answer is None or answer not in product_index:
            continue

        row = scores[i].copy()
        for product_id in bought.get(customer_id, ()):  # 이미 산 상품은 추천 후보에서 제외
            p = product_index.get(product_id)
            if p is not None:
                row[p] = -np.inf

        ranked = [product_ids[p] for p in np.argsort(-row)[:max_k]]
        evaluated += 1
        for k in ks:
            if answer in ranked[:k]:
                hits[k] += 1

    if evaluated == 0:
        return {k: 0.0 for k in ks}
    return {k: hits[k] / evaluated * 100 for k in ks}


def compare_recommendations(
    con: sqlite3.Connection,
    vectors: dict[str, tuple[list, NDArray[np.float32]]],  # check_vector_data가 돌려준 것 그대로
    token_result: dict[str, float], # check_token_sizes 반환값 (지금은 로그용으로만 씀)
) -> dict[str, dict[int, float]]:                          # {label: {k: hit%}}
    """calculate_scores + hit_at을 엮어 3가지 추천 방식의 성능을 한 번에 비교한다. (5단계)"""
    customer_ids, customer_mat = vectors["customer_vectors"]
    product_ids, product_mat = vectors["product_vectors"]
    chunk_ids, chunk_mat = vectors["chunk_vectors"]  # chunk_ids[j] = 그 조각의 purchase_id

    product_of = dict(con.execute("SELECT purchase_id, product_id FROM purchase"))

    bought = defaultdict(set)
    for customer_id, product_id in con.execute("""
        SELECT pe.user_id, pu.product_id
        FROM purchase AS pu
        JOIN pet AS pe ON pe.pet_id = pu.pet_id
        JOIN review AS r ON r.purchase_id = pu.purchase_id
        WHERE r.is_holdout = 0
    """):
        bought[customer_id].add(product_id)

    answers = dict(con.execute("""
        SELECT pe.user_id, pu.product_id
        FROM purchase AS pu
        JOIN pet AS pe ON pe.pet_id = pu.pet_id
        JOIN review AS r ON r.purchase_id = pu.purchase_id
        WHERE r.is_holdout = 1
    """))

    scores = calculate_scores(customer_mat, product_mat, chunk_mat, chunk_ids, product_ids, product_of)

    results = {}
    for label, mat in scores.items():
        results[label] = hit_at(mat, customer_ids, product_ids, bought, answers)
        rates = ", ".join(f"hit@{k}={v:.1f}%" for k, v in results[label].items())
        print(f"[5단계] {label}: {rates}")
    return results

def print_final_result(problems: list[str]) -> None:
    """여섯 단계에서 발견된 문제를 마지막에 모아서 출력하는 함수"""
    if not problems:
        print("전부 통과")
        return
    print(f"문제 {len(problems)}건 ― 앱을 붙이기 전에 고친다")
    for message in problems:
        print(f"  - {message}")
