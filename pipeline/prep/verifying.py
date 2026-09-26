# Last Updated : 2026-09-06

"""만든 것이 쓸 수 있는 물건인지 재는 검사들 + 눈으로 보지 않는 점수 계산.

아무것도 만들지 않는다. CREATE 도 INSERT 도 DROP 도 없어서 몇 번을 돌려도
데이터가 안 바뀐다. 재는 파일의 조건이다.

연결을 인자로 받는다. 부르는 쪽이 이미 하나 열었는데 여기서 또 열면 안 된다.

실패를 problems 목록에 쌓아서 돌려준다. 첫 실패에서 멈추지 않는다.
한 번 돌려서 무엇이 몇 개 틀렸나를 다 보는 것이 점검표의 값이다.
"""

import time
from collections import defaultdict

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import Connection, distinct, func, select
from sqlalchemy import inspect as sa_inspect

from app.core.db import Base
from app.domain.embedding_text import product_text
from app.models import chunk, common, pet, product, purchase, user  # noqa: F401 (Base.metadata 등록용)
from app.models.chunk import Chunk, EmbeddingMeta
from app.models.pet import Pet
from app.models.product import Product
from app.models.purchase import Purchase, Review
from pipeline.prep.chunking import count_tokens


def check(ok: bool, error_msg: str, problems: list[str]) -> bool:
    """
    # Summary
    * 참/거짓을 한 줄로 찍고 실패한 것만 problems 에 쌓는다
    # params
    * ok: 검사 결과
    * error_msg: 찍을 문장. 실패하면 이 문장이 problems 에 쌓인다
    * problems: 실패를 모으는 목록 (부르는 쪽 것을 그대로 고친다)
    # examples
    * (False, 'chunks 테이블이 있다', problems) -> '[문제] ...' 출력, problems 에 문장 추가
    * -> False (ok 를 그대로 돌려줌)
    """
    print(f"  [{'OK  ' if ok else '문제'}] {error_msg}")
    if not ok:
        problems.append(error_msg)
    return ok


def check_table_data(con: Connection, table_names: tuple, problems: list[str]):
    """
    # Summary
    * 표마다 몇 행인가. 벡터가 빠진 행은 없는가. (1단계)
    # params
    * con: 읽을 DB 커넥션
    * table_names: 검사할 테이블 이름들
    * problems: 실패를 모으는 목록
    # examples
    * 테이블 이름들 -> 존재·행 수, 조각 수 == 벡터 수, 홀드아웃 수 == 고객 수 를 확인
    * -> 반환 없음. 결과는 출력되고 실패는 problems 에 쌓임
    """
    existing = set(sa_inspect(con).get_table_names())
    ok_count = 0
    counts = {}
    for name in table_names:
        if not check(name in existing, f"{name} 테이블이 있다", problems):
            continue
        # "user" 같은 Postgres 예약어는 SQLAlchemy 가 알아서 따옴표로 감싼다.
        counts[name] = con.execute(select(func.count()).select_from(Base.metadata.tables[name])).scalar_one()
        if check(counts[name] > 0, f"{name} 테이블에 데이터가 있다 ({counts[name]:,}행)", problems):
            ok_count += 1
    print(f"[1단계] 테이블 {ok_count}/{len(table_names)}개 정상")

    if "chunks" in counts and "chunk_vectors" in counts:
        check(
            counts["chunk_vectors"] == counts["chunks"],
            f"모든 조각에 벡터가 있다 ({counts['chunk_vectors']:,}/{counts['chunks']:,})",
            problems,
        )

    # FK 위반 검사(SQLite 의 PRAGMA foreign_key_check)는 없다. Postgres 는 INSERT 시점에
    # FK 를 강제하므로 위반한 행이 애초에 들어오지 못한다.

    # 채점의 전제다. hit@k는 숨겨 둔 정답이 상위 k 안에 오나를 세는데,
    # 정답이 없으면 셀 것이 없고 그 자리에서 죽는다.
    if "review" in counts and "user" in counts:
        holdout = con.execute(
            select(func.count()).select_from(Review).where(Review.is_holdout == 1)
        ).scalar_one()
        customer_count = con.execute(
            select(func.count(distinct(Pet.user_id))).select_from(Purchase).join(Pet, Pet.pet_id == Purchase.pet_id)
        ).scalar_one()
        check(
            holdout == customer_count,
            f"채점용 정답이 고객당 1건이다 ({holdout}건 / 고객 {customer_count}명)",
            problems,
        )


def check_vector_data(
    con: Connection, kinds: tuple, expected_dim: int, expected_model: str, problems: list[str]
):
    """
    # Summary
    * 벡터를 되살려 차원 · 모델 · 정규화를 본다. (2단계)
    * {표 이름: (아이디, 행렬)} 을 돌려준다
    # params
    * con: 읽을 DB 커넥션
    * kinds: (벡터 테이블, 열쇠 컬럼) 쌍들
    * expected_dim: 설정의 차원 (EMBED_DIM)
    * expected_model: 설정의 모델 (EMBED_MODEL)
    * problems: 실패를 모으는 목록
    # examples
    * KINDS 3벌 -> embedding_meta 의 모델/차원 비교, 각 표의 벡터를 행렬로 읽어 차원·길이 1 확인
    * -> {'chunk_vectors': ([purchase_id, ...], (n, 1536) 행렬), ...}
    """
    meta = dict(con.execute(select(EmbeddingMeta.key, EmbeddingMeta.value)).all())
    check(
        meta.get("model") == expected_model,
        f"모델이 설정값과 같다 (저장값 '{meta.get('model')}', 설정값 '{expected_model}')",
        problems,
    )
    check(
        meta.get("dim") == str(expected_dim),
        f"차원이 설정값과 같다 (저장값 {meta.get('dim')}, 설정값 {expected_dim})",
        problems,
    )

    vectors = {}
    existing = set(sa_inspect(con).get_table_names())
    for table, id_col in kinds:
        # 테이블이 없으면 Postgres 는 트랜잭션째 에러 상태가 되므로 먼저 확인한다.
        if not check(table in existing, f"{table} 테이블이 있다", problems):
            continue
        # vector 컬럼이 Vector 타입이라 pgvector 가 문자열 "[...]" 이 아니라 배열로 풀어 준다.
        t = Base.metadata.tables[table]
        rows = con.execute(select(t.c[id_col], t.c.vector)).all()
        if not check(bool(rows), f"{table}에 벡터가 있다", problems):
            continue

        ids = [row_id for row_id, _ in rows]
        mat = np.array([vec for _, vec in rows], dtype=np.float32)

        check(
            mat.shape[1] == expected_dim,
            f"{table} 차원이 설정값과 같다 (실제 {mat.shape[1]}, 설정값 {expected_dim})",
            problems,
        )
        vectors[table] = (ids, mat)

    # 아래 5단계 비교가 통째로 이 정규화 위에 서 있다. 길이가 1이면 내적이 곧
    # 코사인이라 나눗셈을 안 해도 된다. 길이가 1이 아닌데 내적을 쓰면 긴 벡터가 무조건 이긴다.
    norms = {table: np.linalg.norm(mat, axis=1) for table, (_, mat) in vectors.items()}
    worst = max(abs(n - 1).max() for n in norms.values())
    check(worst < 1e-3, f"전부 길이 1로 정규화돼 있다 (제일 어긋난 것도 {worst:.6f})", problems)

    print(f"[2단계] 모델={meta.get('model')}, 차원={meta.get('dim')}")
    return vectors


def check_vector_storage(
    con: Connection, kinds: tuple, vectors: dict, embed_dim: int, problems: list[str]
) -> dict:
    """
    # Summary
    * 저장된 벡터의 차원이 전부 설정값인지 DB 쪽에서 센다. (3단계)
    # info
    * SQLite 때는 BLOB 바이트 수(dim*4)로 쟀지만, pgvector 는 헤더가 붙고 TOAST 압축도 될 수 있어
      바이트 수가 dim*4 와 안 맞는다. 그래서 vector_dims()로 차원을 직접 센다
    * 바이트 수(pg_column_size)는 용량 참고로만 찍는다
    # params
    * con: 읽을 DB 커넥션
    * kinds: (벡터 테이블, 열쇠 컬럼) 쌍들. 첫 번째 표만 잰다
    * vectors: check_vector_data()가 돌려준 것 (여기선 안 쓴다)
    * embed_dim: 설정의 차원
    * problems: 실패를 모으는 목록
    # examples
    * KINDS 의 첫 표 -> vector_dims() 로 차원이 다른 행 수, pg_column_size 합계를 셈
    * -> {count: 3000, wrong_dim: 0, total_bytes: ...}
    """
    table = kinds[0][0]
    vector = Base.metadata.tables[table].c.vector
    count, wrong_dim, total_bytes = con.execute(
        select(
            func.count(),
            func.count().filter(func.vector_dims(vector) != embed_dim),
            func.coalesce(func.sum(func.pg_column_size(vector)), 0),
        ).select_from(Base.metadata.tables[table])
    ).one()

    check(
        wrong_dim == 0,
        f"{table} 벡터가 전부 {embed_dim}차원이다 (어긋난 것 {wrong_dim}개)",
        problems,
    )

    one_bytes = total_bytes / count if count else 0
    print(
        f"[3단계] {table} {count:,}개, 벡터 하나당 {one_bytes / 1024:.2f}KB, 전체 {total_bytes / 1024:.2f}KB"
    )

    return {"count": count, "wrong_dim": wrong_dim, "total_bytes": total_bytes}


def check_token_sizes(con: Connection, max_tokens: int, problems: list[str]):
    """
    # Summary
    * 상한을 넘어 잘리는 조각이 있는가. (4단계)
    # info
    * 토큰은 글자 수도 낱말 수도 아니고 모델이 글을 나누는 단위다
    * 상한을 넘으면 뒤가 잘린 채로 벡터가 되는데 오류는 안 난다
    # params
    * con: 읽을 DB 커넥션
    * max_tokens: 모델의 토큰 상한
    * problems: 실패를 모으는 목록
    # examples
    * max_tokens=EMBED_MAX_TOKENS -> chunks 의 n_tokens 로 전체·초과·평균을 셈
    * -> {total: 3000, over_limit: 0, average: 87.3}
    """
    total = con.execute(select(func.count()).select_from(Chunk)).scalar_one()
    over = con.execute(select(func.count()).select_from(Chunk).where(Chunk.n_tokens > max_tokens)).scalar_one()
    # Postgres AVG 는 Decimal 을 돌려줘서 float 로 바꿔 둔다.
    average = float(con.execute(select(func.avg(Chunk.n_tokens))).scalar_one() or 0)

    check(over == 0, f"상한({max_tokens})을 넘는 조각 {over}개", problems)
    print(f"[4단계] 조각 평균 {average:.1f}토큰 · 총 {total}개 중 상한 초과 {over}개")

    return {"total": total, "over_limit": over, "average": average}


def calculate_scores(
    customer_vectors: NDArray[np.float32],  # (n_customers, dim)
    product_vectors: NDArray[np.float32],  # (n_products, dim)
    chunk_vectors: NDArray[np.float32],  # (n_chunks, dim)
    chunk_ids: list[int],  # 조각 하나하나가 속한 purchase_id 목록 (product_of 키용)
    product_ids: list[str],  # 상품 ID 리스트 (순서 = product_vectors 행 순서)
    product_of: dict[int, str],  # purchase_id -> product_id 매핑
) -> dict[str, NDArray[np.float32]]:  # 3가지 점수 행렬 (n_customers, n_products)
    """
    # Summary
    * 상품요약/조각최고점/조각평균 3방식으로 (고객 x 상품) 점수 행렬을 만든다. (5단계)
    # info
    * 세 벡터가 전부 정규화돼 있으므로(normalize_embeddings=True) 내적 = 코사인 유사도다
    # params
    * 각 인자의 모양은 시그니처 옆 주석에 있다
    # examples
    * 고객·상품·조각 행렬 -> 고객x상품 내적, 고객x조각 내적을 상품별 max/mean 으로 합침
    * -> {'상품 요약 벡터 (기준선)': (고객, 상품) 행렬, '조각 · max': ..., '조각 · mean': ...}
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
        "상품 요약 벡터 (기준선)": summary_scores,
        "조각 벡터 · max 로 합치기": chunk_max,
        "조각 벡터 · mean 으로 합치기": chunk_avg,
    }


def hit_at(
    scores: NDArray[np.float32],  # (n_customers, n_products)
    customer_ids: list[str],  # 고객 ID 리스트 (scores 행 순서)
    product_ids: list[str],  # 상품 ID 리스트 (scores 열 순서)
    bought: dict[str, set[str]],  # customer_id -> 이미 산 상품들 집합
    answers: dict[str, str],  # customer_id -> 정답 상품 (holdout)
    ks: tuple[int, ...] = (1, 3, 5),
) -> dict[int, float]:  # {k: hit_rate_percent}
    """
    # Summary
    * 점수 행렬에서 고객별 정답 상품이 상위 k 안에 들었는지로 hit@k를 계산한다. (5단계)
    # params
    * 각 인자의 모양은 시그니처 옆 주석에 있다
    # examples
    * 점수 행렬, 정답 {고객: 상품} -> 고객마다 이미 산 상품을 빼고 점수순 상위 k 에 정답이 있나 셈
    * -> {1: 12.3, 3: 25.0, 5: 33.1} (퍼센트)
    """
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
    con: Connection,
    vectors: dict[str, tuple[list, NDArray[np.float32]]],  # check_vector_data가 돌려준 것 그대로
    token_result: dict[str, float],  # check_token_sizes 반환값
) -> dict[str, dict[int, float]]:  # {label: {k: hit%}}
    """
    # Summary
    * calculate_scores + hit_at을 엮어 3가지 추천 방식의 성능을 한 번에 비교한다. (5단계)
    # params
    * con: 읽을 DB 커넥션
    * vectors, token_result: 시그니처 옆 주석 참고
    # examples
    * vectors, token_result -> 이미 산 것/정답을 DB 에서 읽고 calculate_scores + hit_at 실행
    * -> {방식 이름: {1: %, 3: %, 5: %}} 반환 + 비교표 출력
    """
    customer_ids, customer_mat = vectors["customer_vectors"]
    product_ids, product_mat = vectors["product_vectors"]
    chunk_ids, chunk_mat = vectors["chunk_vectors"]  # chunk_ids[j] = 그 조각의 purchase_id

    product_of = dict(con.execute(select(Purchase.purchase_id, Purchase.product_id)).all())

    # 고객이 리뷰를 남긴 구매. is_holdout 으로 이미 산 것(0)과 채점용 정답(1)을 가른다.
    reviewed = (
        select(Pet.user_id, Purchase.product_id)
        .select_from(Purchase)
        .join(Pet, Pet.pet_id == Purchase.pet_id)
        .join(Review, Review.purchase_id == Purchase.purchase_id)
    )

    bought = defaultdict(set)
    for customer_id, product_id in con.execute(reviewed.where(Review.is_holdout == 0)):
        bought[customer_id].add(product_id)

    answers = dict(con.execute(reviewed.where(Review.is_holdout == 1)).all())

    # embed.py/prep_rec.py가 실제로 쓰는 그 함수(product_text)로 다시 문장을 만들어 토큰을 센다.
    # 손으로 다시 조립하면 만들 때와 잴 때가 어긋나도 아무도 모른다.
    product_rows = [dict(row) for row in con.execute(select(Product.__table__)).mappings()]
    average_product_tokens = sum(count_tokens(product_text(row)) for row in product_rows) / len(product_rows)

    average_tokens = {
        "상품 요약 벡터 (기준선)": average_product_tokens,
        "조각 벡터 · max 로 합치기": token_result["average"],
        "조각 벡터 · mean 으로 합치기": token_result["average"],
    }

    started = time.perf_counter()
    scores = calculate_scores(customer_mat, product_mat, chunk_mat, chunk_ids, product_ids, product_of)
    elapsed = time.perf_counter() - started

    print(
        f"[5단계] 고객 {len(customer_ids)}명 · 상품 {len(product_ids)}개 · "
        f"조각 {len(chunk_ids):,}개 전부 비교하는 데 {elapsed * 1000:.0f}ms\n"
    )
    print(f"[5단계] {'무엇으로 찾나':22s} {'평균 토큰':>10s} {'hit@1':>7s} {'hit@3':>7s} {'hit@5':>7s}")

    results = {}
    for label, mat in scores.items():
        results[label] = hit_at(mat, customer_ids, product_ids, bought, answers)
        hits = results[label]
        print(
            f"[5단계] {label:22s} {average_tokens[label]:>10.1f} "
            f"{hits[1]:>6.1f}% {hits[3]:>6.1f}% {hits[5]:>6.1f}%"
        )

    # 읽는 법: 참고파일(docs/measurements.md)은 30명 표본에서 자의 흔들림이 16.7%p
    # 난다고 쟀는데, 그건 그 프로젝트 데이터 얘기라 우리 숫자로 그대로 못 쓴다.
    # 우리는 아직 그 흔들림을 직접 재본 적이 없으니, 결론은 실제 결과가 정하게 둔다.
    best_label = max(results, key=lambda label: results[label][5])
    print(f"\n[5단계] hit@5 기준 제일 나은 방식: {best_label} ({results[best_label][5]:.1f}%)")
    print(f"[5단계] 표본이 {len(customer_ids)}명뿐이라 1~2%p 차이는 표본 흔들림일 수 있으니 참고만 한다.")

    return results


def print_final_result(problems: list[str]) -> None:
    """
    # Summary
    * 쌓아 둔 문제를 한 번에 요약한다. 새로 검사하지 않는다
    # params
    * problems: 앞 단계들이 쌓은 실패 목록
    # examples
    * ['chunks 테이블이 있다'] -> 건수와 문장을 출력. 빈 목록이면 '전부 통과'
    * -> 반환 없음
    """
    print()
    print("=" * 74)
    if problems:
        print(f"문제 {len(problems)}건. 앱을 붙이기 전에 고친다")
        for message in problems:
            print(f"  - {message}")
    else:
        print("전부 통과. 다음은 uvicorn app.main:app --reload")
    print("=" * 74)
