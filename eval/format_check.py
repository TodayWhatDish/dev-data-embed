"""LLM 구조화 출력이 후보 밖 id를 지어내지 않는지 확인한다.

    recommending.recommend()/strategy 쪽에 이미 방지 코드가 있지만, 그게 "실제 모델
    응답"을 상대로도 통하는지는 라이브 호출 없이는 알 수 없다 (프롬프트만 봐서는 모델이
    말을 들을지 안 들을지 보증이 안 됨).
"""
from app.adapters.stores.llm import chat
from app.domain.prompting import Strategy, build_strategy_prompt
from app.features.recommending import recommend


def check_recommend():
    candidates = [
        {'product_id': 1, 'name': '연어 사료', 'price_krw': 30000, 'review': '잘 먹어요'},
        {'product_id': 2, 'name': '닭고기 사료', 'price_krw': 25000, 'review': '보통이에요'},
        {'product_id': 3, 'name': '오리 사료', 'price_krw': 28000, 'review': '설사했어요'},
        {'product_id': 4, 'name': '참치 캔', 'price_krw': 4000, 'review': '좋아해요'},
    ]
    profile = {'animal': '강아지', 'size_category': '소형'}
    picks, retries, error = recommend(candidates, profile, n_pick=2)
    print(f'  recommend: picks={len(picks)}개, retries={retries}, error={error!r}')
    assert error == '', f'recommend 실패: {error}'
    assert len(picks) == 2
    assert all(p['product_id'] in {c['product_id'] for c in candidates} for p in picks)


def check_strategy():
    detail = {
        'name': '홍길동', 'region': '서울',
        'purchases': [
            {'purchase_id': 11, 'product_name': '연어 사료', 'rating': 5, 'review_body': '잘 먹어요'},
            {'purchase_id': 12, 'product_name': '닭고기 사료', 'rating': 3, 'review_body': '그럭저럭'},
        ],
    }
    prompt = build_strategy_prompt(detail)
    result: Strategy = chat.with_structured_output(Strategy).invoke(prompt)
    owned = {p['purchase_id'] for p in detail['purchases']}
    bad = [c.purchase_id for c in result.citations if c.purchase_id not in owned]
    print(f'  strategy: citations={len(result.citations)}개, bad_ids={bad}')
    assert not bad, f'후보 밖 purchase_id를 지어냄: {bad}'


def run():
    check_recommend()
    check_strategy()
    print('format_check OK')


if __name__ == '__main__':
    run()
