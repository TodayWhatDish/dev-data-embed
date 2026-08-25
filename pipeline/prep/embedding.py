# Last Updated : 2026-08-25

"""리뷰 한 건을 임베딩용 문장으로 조립한다.

어떻게 조립하는지만 안다. row가 어디서 왔는지, 이 문장이 이후 어떻게 쓰일지는 모른다.
prepare.py가 이 함수로 문장을 만든 뒤 chunking.split_reviews()에 넘긴다.
"""

import sqlite3


def build_doc(row: sqlite3.Row) -> str:
    """리뷰 한 건을 임베딩용 문장으로 조립한다."""
    """[미구현]"""
    pass
