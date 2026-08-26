# Last Updated : 2026-08-26

""" 문서 목록을 벡터로 바꾼다.

리뷰+펫 프로필 + 제품 정보를 임베딩용 단일 문장으로 조립한다. 이 문장이 벡터화 되어 review_vector에 저장되고, 검색 시 쿼리와 비교한다.
"""

import sqlite3
from app.core.config import BATCH_SIZE
from app.core.embedder import get_embeddings


def build_review_doc(row: sqlite3.Row) -> str:
    """리뷰 한 건을 임베딩용 문장으로 조립한다."""
    allergy = row["allergy"] or "알레르기 없음"
    health = row["health_condition"] or "건강 특이사항 없음"
    return (
        "passage:\n"
        f"{row['size_category']}견 {row['age_group']} {row['breed']}, {allergy}, {health}. "
        f"{row['category']}/{row['sub_category']} {row['product_name']} "
        f"({row['target_feeding_purpose']} 목적, {row['target_food_form']}) "
        f"별점 {row['rating']}점 후기: {row['review']}"
    )
