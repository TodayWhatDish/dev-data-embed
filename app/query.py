# Last updated: 2026-09-03
# 프로필 + 질문을 받아 유사 리뷰를 찾아주는 대화형 확인용 CLI
#
# 검색 로직 자체는 search.py 에 있다. 여기서는 입력을 받고 결과를 찍고 로그를 남기는 일만 한다.
import json
import sqlite3
from datetime import datetime
from app.core.config import LOG_PATH, PASSAGE_PREFIX
from app.core.config import SIZE_LABELS
from app.features.retrieve import build_where,fmt_purchase_id
from pipeline.vector_db import search,connect  
from app.features.profile import list_pets, pet_profile

def log_result(profile, query, hits):
    record = {
        'time': datetime.now().isoformat(timespec='seconds'),
        'profile': profile,
        'query': query,
        'hits': [
            {'id': fmt_purchase_id(pid), 'score': round(score, 3), 'doc': doc.removeprefix(PASSAGE_PREFIX)}
            for pid, score, doc in hits
        ],
    }

    # 'a'(append) 모드라 기존 로그를 안 지우고 계속 뒤에 붙입니다. 
    # ensure_ascii=False가 없으면 한글이 \uXXXX로 저장돼서 눈으로 못 읽게됨
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False,indent=2) + '\n')

def choose_pet():
    """user_id 를 받아 그 사용자의 펫 하나를 고르게 한다. 못 고르면 None."""
    raw = input('user_id: ').strip()
    if not raw.isdigit():
        print('  숫자로 입력하세요.')
        return None

    pets = list_pets(int(raw))
    if not pets:
        print('  등록된 펫이 없습니다.')
        return None

    print('\n누구의 상품을 추천받을까요?')
    for pet in pets:
        allergies = pet['allergies'] or '없음'
        size_label = SIZE_LABELS.get(pet['size'], '체급 미등록')
        print(f"  [{pet['pet_id']}] {pet['name']} "
              f"({pet['animal_category']}, {size_label}, 알레르기: {allergies})")

    picked = input('pet_id: ').strip()
    if not any(str(pet['pet_id']) == picked for pet in pets):
        print('  목록에 없는 pet_id 입니다.')
        return None
    return int(picked)


def main():
    con = connect()
    # 모델 로딩과 벡터 읽기를 여기서 한 번만 치른다. 이후 질문은 이 캐시를 재사용한다.

    pet_id = None
    while pet_id is None:
        pet_id = choose_pet()

    profile = pet_profile(pet_id)   # 종/체급/알레르기를 DB 에서 확정한다. 사람이 다시 안 친다.
    print(f'\n적용된 프로필: {profile}')

    print('질문을 입력하세요 (빈 줄 입력 시 종료)')
    while True:
        query = input('\n질문: ').strip()
        if not query:
            break

        where, params = build_where(profile)
        hits = search(con, query, where=where, params=params)

        for pid, score, doc in hits:
            text = doc.removeprefix(PASSAGE_PREFIX)
            print(f'\n  [{fmt_purchase_id(pid)}] 유사도 {score:.3f}')
            print(f'  {text}')

        log_result(profile, query, hits)

    con.close()

if __name__ == '__main__':
    main()
