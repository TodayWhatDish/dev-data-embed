# Last Updated : 2026-08-23

""" 리뷰를 임베딩용 문서로 조립하고 토큰 한도에 맞게 자른다. 벡터는 안 만든다 - build_index.py가 한다.

    자르는 건 몇 초, 임베딩은 모델 로딩 포함 수십 초 - 값이 다른 작업이라 나눴다.
"""

import sqlite3
import statistics
import sys
from pathlib import Path

from transformers import logging as hf_logging

# 터미널에 출력할 수 없는 특수 이모지나 기호 등을 대체문자로 변경하여 오류를 방지
sys.stdout.reconfigure(errors="replace")

# 청킹하는 문자가 최대 토큰수를 넘어설 때 지저분하게 발생하는 에러 권고사항을 꺼줌.
# 중요한 에러 문구는 그대로 출력 처리
hf_logging.set_verbosity_error()

from app.core.config import DB_PATH,INDEX_FILTER
from pipeline.prep import chunking, storage

def build_doc(row:str):
    """리뷰 한 건에 대해서 임베딩용 문장으로 조립한다."""
    """[미구현]"""
    pass

def fetch_rows(cur:sqlite3.Row):
    """자를 대상 리뷰를 상품 정보와 함께 읽어온다. (대상 조건인 INDEX_FILTER는 config.py에 명시)"""
    """[미구현]"""
    pass

def main():
    """[미구현]"""
    con = sqlite3.connect(DB_PATH)
    row = fetch_rows(con.cursor())
    con.clese()

if __name__ == '__main__':
    main()


