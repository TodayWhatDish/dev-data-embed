# Last updated: 2026-09-03
"""증분 임베딩이 '실제 쓰기 경로'로 들어온 리뷰 한 건만 다시 임베딩하는지 확인한다.

CSV 를 고쳐 load_csv 로 확인할 수가 없다 - 전체 재적재는 DB 를 통째로 새로 만들어서
'딱 한 건만 늘었다' 를 볼 수 없기 때문이다. 회원가입 경로가 쓰는 insert_query 로
purchase/review 까지 직접 넣어 조각을 하나만 늘린다.

    py -m tests.incremental_embed setup
    py -m pipeline.chunk      # 조각 +1
    py -m pipeline.embed      # 새로 1 / 그대로 N / 지움 0
    py -m tests.incremental_embed cleanup
    py -m pipeline.chunk      # 조각 -1
    py -m pipeline.embed      # 새로 0 / 그대로 N / 지움 1
"""
import logging
import sys

from app.app_logger.logger import init_logger
from app.core.db import execute, fetch_one
from app.core.security import hash_password
from app.repositories.general_query.insert import insert_query
from app.repositories.pet import create_pet
from app.repositories.users import create_user, find_user_by_email

logger = logging.getLogger()

EMAIL = '__test_embed__@example.com'


def chunk_count():
    return fetch_one('SELECT COUNT(*) AS n FROM chunks')['n']


def setup():
    assert find_user_by_email(EMAIL) is None, '이전 실행의 흔적이 남아있다 - cleanup 을 먼저 돌려라'

    user_id = create_user(email=EMAIL, name='임베딩테스트',
                          password_hash=hash_password('pw12345'))
    pet_id = create_pet(user_id=user_id, animal_category_id=1, name='테스트펫', size=3)

    # purchase 와 review 는 전용 함수가 없다. 회원가입이 쓰는 것과 같은 범용 INSERT 로 넣는다.
    purchase_id = insert_query('purchase', {
        'pet_id': pet_id, 'product_id': 1, 'unit_price_krw': 10000,
        'purchased_at': '2026-09-03 12:00:00',
    })
    insert_query('review', {
        'purchase_id': purchase_id, 'rating': 5,
        'body': '증분 임베딩 테스트용 리뷰입니다. 아이가 아주 잘 먹고 소화도 잘 시킵니다.',
        'reviewed_at': '2026-09-03 12:00:00',
    })
    # is_holdout 은 안 넣는다 - 기본값 0 이라 그대로 색인 대상이 된다.

    logger.info(f'\t넣음 user={user_id} pet={pet_id} purchase={purchase_id}')
    logger.info(f'\t지금 chunks {chunk_count()}개 -> chunk.py 를 돌리면 +1')


def cleanup():
    row = find_user_by_email(EMAIL)
    if row is None:
        logger.info('\t지울 것이 없다')
        return
    user_id = row['user_id']

    # FK 를 거스르지 않게 자식부터 지운다. review -> purchase -> pet -> user.
    execute("""DELETE FROM review WHERE purchase_id IN (
                   SELECT pu.purchase_id FROM purchase AS pu
                   JOIN pet AS pe ON pe.pet_id = pu.pet_id WHERE pe.user_id = ?)""", (user_id,))
    execute('DELETE FROM purchase WHERE pet_id IN (SELECT pet_id FROM pet WHERE user_id = ?)', (user_id,))
    execute('DELETE FROM pet WHERE user_id = ?', (user_id,))
    execute('DELETE FROM user WHERE user_id = ?', (user_id,))

    assert find_user_by_email(EMAIL) is None
    logger.info(f'\t정리 완료 - 지금 chunks {chunk_count()}개 -> chunk.py 를 돌리면 -1')


if __name__ == '__main__':
    init_logger('incremental_embed')
    step = sys.argv[1] if len(sys.argv) > 1 else 'setup'
    {'setup': setup, 'cleanup': cleanup}[step]()
    logger.info('ok')
