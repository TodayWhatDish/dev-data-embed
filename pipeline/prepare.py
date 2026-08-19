# Last Updated : 2026-08-19

import sqlite3
import statistics
import sys
from pathlib import Path

from transformers import AutoTokenizer, logging as hf_logging
# 터미널에 출력할 수 없는 특수 이모지나 기호 등을 대체문자로 변경하여 오류를 방지
sys.stdout.reconfigure(errors="replace")

# 청킹하는 문자가 최대 토큰수를 넘어설 때 지저분하게 발생하는 에러 권고사항을 꺼줌.
# 중요한 에러 문구는 그대로 출력 처리
hf_logging.set_verbosity_error()