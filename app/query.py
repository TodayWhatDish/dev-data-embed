# Last updated: 2026-08-27
# 프로필 + 질문을 받아 유사 리뷰를 찾아주는 대화형 확인용 CLI
#
# 검색 로직 자체는 search.py 에 있다. 여기서는 입력을 받고 결과를 찍고 로그를 남기는 일만 한다.
import json
import sqlite3
from datetime import datetime
from app.core.config import LOG_PATH
from app.features.retrieve import build_where,fmt_purchase_id
from pipeline.vector_db import search,connect  
from app.features.profile import build_profile

def log_result(profile, query, hits):
    record = {
        'time': datetime.now().isoformat(timespec='seconds'),
        'profile': profile,
        'query': query,
        'hits': [
            {'id': fmt_purchase_id(pid), 'score': round(score, 3), 'doc': doc.removeprefix('passage: ')}
            for pid, score, doc in hits
        ],
    }

    # 'a'(append) 모드라 기존 로그를 안 지우고 계속 뒤에 붙입니다. 
    # ensure_ascii=False가 없으면 한글이 \uXXXX로 저장돼서 눈으로 못 읽게됨
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False,indent=2) + '\n')

def main():
    con = connect()
    # 모델 로딩과 벡터 읽기를 여기서 한 번만 치른다. 이후 질문은 이 캐시를 재사용한다.

    print('질문을 입력하세요 (빈 줄 입력 시 종료)')
    while True:
        query = input('\n질문: ').strip()
        if not query:
            break
        species = input('  종(개/고양이, 생략 가능): ').strip()
        size = input('  체급(초소형/소형/중형/대형/초대형, 생략 가능): ').strip()
        allergy = input('  알레르기(예: 닭고기 알레르기, 생략 가능): ').strip()

        profile = {}
        if species:
            profile['animal_category'] = species
        if size:
            profile['size_category'] = size
        if allergy:
            profile['allergy'] = allergy

        profile = build_profile(profile)
        where, params = build_where(profile)
        hits = search(con, query, where=where, params=params)

        for pid, score, doc in hits:
            text = doc.removeprefix('passage: ')
            print(f'\n  [{fmt_purchase_id(pid)}] 유사도 {score:.3f}')
            print(f'  {text}')

        log_result(profile, query, hits)

    con.close()

if __name__ == '__main__':
    main()
