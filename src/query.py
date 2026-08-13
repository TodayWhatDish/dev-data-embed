import json
import sqlite3
from datetime import datetime

from sentence_transformers import SentenceTransformer

from config import DB_PATH,MODEL_NAME,ROOT,LOG_PATH
from embed import fmt_purchase_id,search

FILTERS = {
    'size_category': 'p.size_category = ?',
    'allergy': '(p.allergy IS NULL OR p.allergy <> ?)',
}

# profile 에 값이 있는 키만 조건절로 바꿈. 
# 아무것도 없다면 '1=1'(조건없음)을 리턴해서 search()가 받을 수 있도록 함
def build_where(profile):
    clauses,params = [],[]
    for key, clause in FILTERS.items():
        if profile.get(key):
            clauses.append(clause)
            params.append(profile[key])

    return ' AND '.join(clauses) or '1=1', tuple(params)


def log_result(profile, query, hits):
    record = {
        'time': datetime.now().isoformat(timespec='seconds'),
        'profile': profile,
        'query': query,
        'hits': [
            {'id': fmt_purchase_id(pid), 'score': round(score, 3), 'doc': doc}
            for pid, score, doc in hits
        ],
    }

    # 'a'(append) 모드라 기존 로그를 안 지우고 계속 뒤에 붙입니다. 
    # ensure_ascii=False가 없으면 한글이 \uXXXX로 저장돼서 눈으로 못 읽게됨
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False,indent=2) + '\n')


def main():
    con = sqlite3.connect(DB_PATH)
    model = SentenceTransformer(MODEL_NAME)

    print('질문을 입력하세요 (빈 줄 입력 시 종료)')
    while True:
        query = input('\n질문: ').strip()
        if not query:
            break
        size = input('  체급(소형/중형/대형, 생략 가능): ').strip()
        allergy = input('  알레르기(예: 닭고기 알레르기, 생략 가능): ').strip()

        profile = {}
        if size:
            profile['size_category'] = size
        if allergy:
            profile['allergy'] = allergy

        where, params = build_where(profile)
        hits = search(con, model, query, where=where, params=params)

        for pid, score, doc in hits:
            print(f'  - {fmt_purchase_id(pid)} ({score:.3f}) {doc[:80]}...')

        log_result(profile, query, hits)

    con.close()


if __name__ == '__main__':
    main()
