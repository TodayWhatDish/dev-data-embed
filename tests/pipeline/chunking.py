import logging

from app.app_logger.logger import init_logger
from pipeline.prep.chunking import build_review_doc, count_tokens, split_review
from pipeline.prep.options import CHUNK_SIZE

logger = logging.getLogger()

ROW = {
    'category': '사료', 'sub_category': '건식사료', 'product_name': '테스트사료',
    'target_feeding_purpose': '체중관리', 'target_food_form': '건식',
    'ingredients': '닭고기, 현미', 'rating': 5, 'review': '아이가 잘 먹어요.',
}


if __name__ == '__main__':
    init_logger('test_chunking')

    # build_review_doc - 필수 필드가 전부 본문에 들어간다
    doc = build_review_doc(ROW)
    for piece in ('사료/건식사료', '테스트사료', '체중관리 목적', '건식', '주원료: 닭고기, 현미', '별점 5점', '아이가 잘 먹어요.'):
        assert piece in doc, (piece, doc)
    logger.info(doc)

    # target_feeding_purpose 가 없으면 '목적 미기재', ingredients 가 없으면 그 자리가 빈다
    bare = dict(ROW, target_feeding_purpose=None, ingredients=None)
    bare_doc = build_review_doc(bare)
    assert '목적 미기재' in bare_doc, bare_doc
    assert '주원료' not in bare_doc, bare_doc
    logger.info('#' * 20)

    # 한도 안이면 조각 1개 그대로
    short_chunks = split_review(1, doc, ROW['product_name'])
    assert len(short_chunks) == 1
    assert short_chunks[0]['n_tokens'] == count_tokens(doc)
    assert short_chunks[0]['chunk_index'] == 0
    logger.info(f'짧은 문서: {len(short_chunks)}개 / {short_chunks[0]["n_tokens"]} 토큰')

    # 한도를 넘으면 여러 조각으로, 각 조각 앞에 상품명이 다시 붙는다
    long_doc = doc + ' 아주 잘 먹습니다.' * 200
    assert count_tokens(long_doc) > CHUNK_SIZE, '테스트 문서가 한도를 못 넘겼다 - 반복 횟수를 늘려라'
    long_chunks = split_review(2, long_doc, ROW['product_name'])
    assert len(long_chunks) > 1, '한도를 넘겼는데 안 쪼개졌다'
    assert [c['chunk_index'] for c in long_chunks] == list(range(len(long_chunks)))
    assert all(c['body'].startswith(f'[{ROW["product_name"]}]') for c in long_chunks)
    # 뒤가 조용히 잘려나가면 안 된다 - 자른 각 조각도 한도 안이어야 한다
    assert all(c['n_tokens'] <= CHUNK_SIZE for c in long_chunks), [c['n_tokens'] for c in long_chunks]
    logger.info(f'긴 문서: {len(long_chunks)}개 조각, 토큰수 {[c["n_tokens"] for c in long_chunks]}')
    logger.info('#' * 20)

    logger.info('chunking self-check OK')
