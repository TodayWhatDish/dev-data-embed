# Last Updated : 2026-08-26
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
import sys
from pathlib import Path

KINDS = ()

TABLE_NAMES = ()