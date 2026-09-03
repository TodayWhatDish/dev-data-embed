import logging

from app.app_logger.logger import init_logger
from pipeline.eval.eval import noise_band, rank_of_answer, summarize

logger = logging.getLogger()


if __name__ == '__main__':
    init_logger('test_eval_metrics')

    # rank_of_answer - 정답이 있으면 1부터 시작하는 순위, 없으면 None
    product_of = {10: 100, 11: 100, 12: 200}
    results = [(11, 0.9, 'r1'), (10, 0.8, 'r2'), (12, 0.7, 'r3')]
    assert rank_of_answer(product_of, 100, results) == 1, '11번이 1등이고 100번 상품이니 1위여야 한다'
    assert rank_of_answer(product_of, 200, results) == 3
    assert rank_of_answer(product_of, 999, results) is None
    logger.info('rank_of_answer ok')
    logger.info('#' * 20)

    # summarize - recall@k 는 순위 <= k 인 비율, mrr 은 순위의 역수 평균
    records = [{'purchase_id': 1, 'product_id': 100, 'rank': 1},
               {'purchase_id': 2, 'product_id': 200, 'rank': 3},
               {'purchase_id': 3, 'product_id': 300, 'rank': None}]
    metrics = summarize(records, ks=(1, 3))
    assert metrics['n'] == 3
    assert metrics['recall@1'] == 1 / 3, metrics
    assert metrics['recall@3'] == 2 / 3, metrics
    assert metrics['mrr'] == (1 / 1 + 1 / 3) / 3, metrics
    logger.info(f'summarize: {metrics}')
    logger.info('#' * 20)

    # k가 커질수록 recall 은 줄어들 수 없다
    for k1, k2 in zip((1, 3), (3, 10)):
        assert summarize(records, ks=(k1, k2))[f'recall@{k1}'] <= summarize(records, ks=(k1, k2))[f'recall@{k2}']

    # noise_band - 전부 맞혔으면(1) 흔들릴 구간이 없다, 전부 틀렸으면(0) 마찬가지
    all_hit = [{'rank': 1}] * 66
    low, high = noise_band(all_hit, k=3, trials=500)
    assert low == high == 1.0, (low, high)

    all_miss = [{'rank': None}] * 66
    low, high = noise_band(all_miss, k=3, trials=500)
    assert low == high == 0.0, (low, high)

    # 섞이면 구간 폭이 생기고, 항상 low <= high
    mixed = [{'rank': 1 if i % 2 == 0 else None} for i in range(66)]
    low, high = noise_band(mixed, k=3, trials=2000, seed=0)
    assert 0.0 <= low <= high <= 1.0, (low, high)
    # 같은 seed면 항상 같은 구간 - 재현 안 되면 모델 비교에 못 쓴다
    assert noise_band(mixed, k=3, trials=2000, seed=0) == (low, high)
    logger.info(f'noise_band(mixed): {low:.1%} ~ {high:.1%}')
    logger.info('#' * 20)

    logger.info('eval metrics self-check OK')
