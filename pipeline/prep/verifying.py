# Last Updated : 2026-08-26

"""파이프라인 결과를 실제로 검사하는 함수들을 모아둔다.

검증 방법을 담당하며, @verify.py는 필요한 값을 준비하고 이 함수들을 순서대로 호출한다.
"""

import time
import numpy as np
import sqlite3
from numpy.typing import NDArray
from app.core.db import load_vectors
from pipeline.prep import chunking, embedding

def check(ok: bool,error_msg: str,problems: list[str]):
    """검사 방법은 알지 못하고, 들어오는 조건에 대한 참/거짓만을 판단."""
    pass

def check_table_data(con: sqlite3.Connection, table_names: str, problems: list[str]):
    """[미구현]"""
    pass

def check_vector_data(con: sqlite3.Connection, kinds: tuple, expected_dim: int, expected_model: str,problems: list[str]):
    """[미구현]"""
    pass

def check_vector_storage(con: sqlite3.Connection, kinds: tuple, vectors: dict, embed_dim: int):
    """[미구현]"""
    pass

def check_token_sizes(con: sqlite3.Connection, max_tokens: int, problems: list[str]):
    """[미구현]"""
    pass

def calculate_scores(
    customer_vectors: NDArray[np.float32],      # (n_customers, dim)
    product_vectors: NDArray[np.float32],       # (n_products, dim)
    chunk_vectors: NDArray[np.float32],         # (n_chunks, dim)
    chunk_ids: list[int],                       # 청크 ID 리스트 (product_of 키용)
    product_ids: list[str],                     # 상품 ID 리스트 (순서 = product_vectors 행 순서)
    product_of: dict[int, str],                 # chunk_id -> product_id 매핑
) -> dict[str, NDArray[np.float32]]:            # 3가지 점수 행렬 (n_customers, n_products)
    """[미구현]"""
    pass


def hit_at(
    scores: NDArray[np.float32],                # (n_customers, n_products)
    customer_ids: list[str],                    # 고객 ID 리스트 (scores 행 순서)
    product_ids: list[str],                     # 상품 ID 리스트 (scores 열 순서)
    bought: dict[str, set[str]],                # customer_id -> 이미 산 상품들 집합
    answers: dict[str, str],                    # customer_id -> 정답 상품 (holdout)
    ks: tuple[int, ...] = (1, 3, 5),
) -> dict[int, float]:                          # {k: hit_rate_percent}
    """[미구현]"""
    pass

def compare_recommendations(
    con: sqlite3.Connection,
    vectors: dict[str, tuple[list, NDArray[np.float32]]],  # {"customer": (ids, mat), ...}
    token_result: dict[str, float], # check_token_sizes 반환값
) -> dict[str, dict[int, float]]:                          # {label: {k: hit%}}
    """[미구현]"""
    pass

def search_any(
    con: sqlite3.Connection,
    kind: str,
    questions: list,
    top_k: int=3,
    wosk: bool=False,
):
    """[미구현]"""
    pass

def print_final_result(problems: list[str]) -> None:
    """여섯 단계에서 발견된 문제를 마지막에 모아서 출력하는 함수"""
    if problems:
        print(f"문제 {len(problems)}건 ― 앱을 붙이기 전에 고친다")
    for message in problems:
      print(f"  - {message}")
    else:
        print("전부 통과")
    