# Last updated: 2026-09-03
"""app/repositories/users.py, pet.py 에 새로 추가한 쓰기 경로(회원가입) 자체 점검.

실제 DB(data/pet_reco.db)에 행을 하나 넣었다가 확인 후 지운다 - UNIQUE(email) 같은 실제 제약까지
타는지 보려면 메모리 DB로는 부족해서다. 끝나면 흔적을 남기지 않는다.
"""
import logging

from app.app_logger.logger import init_logger
from app.core.db import execute
from app.core.security import hash_password, verify_password
from app.repositories.pet import create_pet
from app.repositories.users import create_user, find_user_by_email

logger = logging.getLogger()

if __name__ == '__main__':
    init_logger('signup_repo')

    email = '__test_signup__@example.com'
    assert find_user_by_email(email) is None, '이전 실행의 흔적이 안 지워졌다'

    user_id = create_user(email=email, name='테스트유저', password_hash=hash_password('pw12345'))
    row = find_user_by_email(email)
    assert row and row['user_id'] == user_id
    assert verify_password('pw12345', row['password_hash'])
    logger.info(f'\tcreate_user -> user_id={user_id}')

    pet_id = create_pet(user_id=user_id, animal_category_id=1, name='테스트펫', size=3)
    logger.info(f'\tcreate_pet  -> pet_id={pet_id}')

    execute('DELETE FROM pet WHERE pet_id = ?', (pet_id,))
    execute('DELETE FROM user WHERE user_id = ?', (user_id,))
    assert find_user_by_email(email) is None
    logger.info('\t정리 완료 - 실제 DB에 흔적 없음')

    logger.info('ok')
