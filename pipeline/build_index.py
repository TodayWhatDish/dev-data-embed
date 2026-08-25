# Last Updated : 2026-08-25

""" chunks 테이블의 조각을 문장 임베딩 벡터로 변환해 chunk_vectors 테이블에 저장한다.

    조각을 만드는 일은 prepare.py 가 한다. 여기는 그 결과를 읽어 벡터로 바꾸기만 한다.
    자르는 건 몇 초, 임베딩은 모델 로딩 포함 수십 초 - 값이 다른 작업이라 나눠 두었다.
    한 파일에 두면 자른 결과만 확인하고 싶을 때도 임베딩을 통째로 다시 만들게 된다.

    이 파일은 지휘만 한다.
    어떻게 벡터로 바꾸는지는 prep/embedding.py 가 알고,
    어디에 어떤 모양으로 넣는지는 prep/storage.py 가 안다.
    여기는 그 둘을 순서대로 부르고, 둘 다 모르는 값(색인 대상의 지문)만 계산해 넘긴다.

    검색은 query.py 를 쓴다.
"""

import sqlite3
import sys

# 터미널에 출력할 수 없는 특수 이모지나 기호 등을 대체문자로 변경하여 오류를 방지
sys.stdout.reconfigure(errors="replace")

from app.core.config import DB_PATH, EMBED_MODEL
from app.core.db import source_fingerprint
from pipeline.prep import embedding, storage


def main():
    con = sqlite3.connect(DB_PATH)
    chunks = storage.load_chunks(con)
    if not chunks:
        raise SystemExit('색인할 조각이 없습니다. 먼저 prepare.py 를 실행하세요.')

    # 읽은 순서 그대로 인코딩한다. save_vectors 가 조각과 벡터를 자리로 짝지으므로
    # 여기서 순서를 바꾸거나 일부만 걸러내면 엉뚱한 조각에 벡터가 붙는다.
    vectors = embedding.embed_texts([chunk['body'] for chunk in chunks])

    # source(색인 대상 데이터의 지문)는 부르는 쪽인 여기서 계산해 넘긴다.
    # storage 는 무엇을 넣을지만 알고 그게 어디서 왔는지는 모르는 자리이기 때문이다.
    storage.save_vectors(con, chunks, vectors, vectors.shape[1], source_fingerprint(con))

    # 조각 수와 리뷰 수를 함께 찍는다. 한 리뷰가 조각 여러 개로 쪼개지므로
    # 조각 수만 봐서는 몇 건을 색인했는지 알 수 없다.
    reviews = len({chunk['purchase_id'] for chunk in chunks})
    print(f'\n조각 {len(chunks)}개 (리뷰 {reviews}건), 차원 {vectors.shape[1]}, 모델 {EMBED_MODEL}')
    print('검색은 query.py 를 실행하세요.')

    con.close()


if __name__ == '__main__':
    main()
