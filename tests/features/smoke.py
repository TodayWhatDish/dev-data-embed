"""features 층이 실제로 도는지 한 번에 훑는다.

관리자 UI 도 로그인도 안 거치고 feature 함수를 직접 부른다. 라우트를 안 타므로 HTTP 상태는
안 본다 — 그건 웹으로 확인할 몫이고, 여기서 보는 건 하나다:
**features 함수가 repositories 를 거쳐 DB 까지 갔다 오는가.**

읽기만 하는 게 대부분이고, 쓰는 구간(4번)은 만든 행을 finally 에서 반드시 지운다.
끝에 DB 가 시작 때와 같은지 대조해서, 테스트가 흔적을 남기지 않았는지 확인한다.

느린 건 마지막 5번뿐이다 (임베딩 모델을 올린다). 앞이 깨지면 거기서 먼저 멈춘다.

    py -m tests.features.smoke
"""
import logging

from app.app_logger.logger import init_logger

init_logger('test_features')

from app.api.lifespan import load_domain_cache, load_schema_cache
from app.core.db import fetch_tuple_one
from app.features import products as product_feat
from app.features import profile, retrieve, searching
from app.features.metric.sqlbench import elapsed_time
from app.features.products import ProductError
from app.repositories import products as product_repo

logger = logging.getLogger()


def raises(kind, fn, *args):
    """그 kind 로 ProductError 가 나는지 본다. 통과했거나 kind 가 다르면 실패다.

    '터졌다' 만 보면 엉뚱한 이유로 터져도 통과해버린다. kind 까지 봐야 의미가 있다
    (tests/features/products.py 의 rejects 와 같은 이유, 예외 종류만 다르다).
    """
    try:
        fn(*args)
    except ProductError as e:
        assert e.kind == kind, f'kind 가 다르다: {e.kind} != {kind}'
        logger.info(f'\t{kind:12} <- {e.message}')
        return
    raise AssertionError(f'ProductError({kind}) 가 나야 하는데 통과했다')


def timed(label, fn):
    """부르고 걸린 시간을 남긴다. features 호출 인터페이스를 재는 게 metric/sqlbench 의 목적이다."""
    with elapsed_time(quiet=True) as t:
        got = fn()
    logger.info(f'\t{label:34} {t.ms:7.2f} ms')
    return got


if __name__ == '__main__':

    # ------------------------------------------------------------------ 1
    logger.info('1. 기동 적재 - 이게 안 되면 뒤는 전부 무의미하다')

    # main.py 가 uvicorn 으로 뜰 때 lifespan 이 부르는 것과 같은 함수다.
    # 이걸 빼면 CommonMgr 이 빈 채로 남아 3번의 resolve_allergy 가 AttributeError 로 죽는다
    load_domain_cache()
    tables = load_schema_cache()
    assert len(tables) > 0, '테이블이 하나도 없다'
    logger.info('#' * 20)

    before = fetch_tuple_one('SELECT count(*), sum(price_krw) FROM product')

    # ------------------------------------------------------------------ 2
    logger.info('2. profile - 펫 정보를 검색 프로필로 바꾼다')

    user_id, pet_id = fetch_tuple_one(
        'SELECT user_id, pet_id FROM pet WHERE inactive_at IS NULL ORDER BY pet_id LIMIT 1')

    pets = timed(f'list_pets({user_id})', lambda: profile.list_pets(user_id))
    assert pets, '활성 펫이 있어야 아래를 볼 수 있다'
    # 조인 결과가 dict 로 와야 화면이 컬럼 이름으로 꺼내 쓴다
    assert {'pet_id', 'name', 'animal_category', 'size'} <= set(pets[0]), pets[0]

    prof = timed(f'pet_profile({pet_id})', lambda: profile.pet_profile(pet_id))
    assert 'animal_category' in prof, prof
    logger.info(f'\t프로필: {prof}')

    # 없는 펫은 예외가 아니라 빈 프로필이다 (필터를 안 거는 것과 같아진다)
    assert profile.pet_profile(-1) == {}
    assert profile.list_pets(-1) == []

    # 자유 텍스트 -> 프로필. 등록 안 된 알레르기는 조용히 빠지고 경고만 남는다
    assert profile.resolve_allergy('없는알러지xyz') is None
    built = profile.build_profile({'animal_category': '개', 'allergy': '소고기 알레르기'})
    assert built.get('allergy'), built
    logger.info(f'\t자유입력 -> {built}')
    logger.info('#' * 20)

    # ------------------------------------------------------------------ 3
    logger.info('3. retrieve - 프로필을 WHERE 절로 조립한다')

    where, params = retrieve.build_where({'animal_category': '개', 'allergy': ['소고기', '닭고기']})
    # 알레르기가 2개면 조건절도 2번 붙어야 한다. 하나만 걸면 나머지 알레르겐이 그대로 통과한다
    assert len(params) == 3, params
    assert 'r.rating >=' in where

    # 아무 조건도 없으면 '조건 없음' 이지 깨진 SQL 이 아니다
    empty_where, empty_params = retrieve.build_where({})
    assert empty_params == () and 'r.rating >=' in empty_where

    problems = retrieve.check_freshness(searching.connect())
    logger.info(f'\t색인 신선도: {problems or "이상 없음"}')
    logger.info('#' * 20)

    # ------------------------------------------------------------------ 4
    logger.info('4. products - 관리자 CRUD 의 경계')

    # 없는 상품은 404 로 이어질 not_found 다 (repositories 는 None 을 줬고 여기서 예외가 된다)
    raises('not_found', product_feat.get_product, -1)

    # page/size 는 클라이언트가 보낸 값이라 서버 버그가 아니다 -> params_error(400)
    raises('params_error', product_feat.list_products, 0, 0)
    raises('params_error', product_feat.list_products, -1, 5)

    # 페이지가 겹치면 목록에 같은 상품이 두 번 뜬다. find_page 의 ORDER BY 가 그걸 막는다
    page0 = product_feat.list_products(0, 5)
    page1 = product_feat.list_products(1, 5)
    ids0, ids1 = [p['product_id'] for p in page0], [p['product_id'] for p in page1]
    logger.info(f'\t0페이지 {ids0} / 1페이지 {ids1}')
    assert not (set(ids0) & set(ids1)), '페이지가 겹친다'

    # 마지막 페이지 다음은 에러가 아니라 빈 목록이다
    assert product_feat.list_products(99999, 5) == []

    product_id = None
    try:
        # 등록 -> 다시 조회까지가 create_product 한 덩어리다. DB DEFAULT 가 채운 값을 보려면 재조회해야 한다
        category_id = product_repo.get_product_categories()[0]['product_category_id']
        created = product_feat.create_product({
            'product_category_id': category_id, 'brand': '테스트브랜드',
            'name': '__스모크테스트__', 'price_krw': 1000, 'weight_g': 500})
        product_id = created['product_id']
        assert created['is_active'] == 1 and created['created_at'], created
        logger.info(f'\t등록 {product_id}: {created["name"]} / active={created["is_active"]}')

        # 수정 -> 재조회. 존재 여부는 선조회가 아니라 고친 행 수로 안다
        rows, after_update = product_feat.update_after_select_product(product_id, {'price_krw': 2000})
        assert rows == 1 and after_update['price_krw'] == 2000, after_update

        # 빈 바디 PATCH 는 'SET  WHERE' 라는 깨진 SQL 이 되므로 features 에서 막는다
        raises('params_error', product_feat.update_product, product_id, {})

        # DB CHECK 위반은 sqlite3 예외가 아니라 ProductError 로 번역돼 올라온다
        raises('params_error', product_feat.update_product, product_id, {'price_krw': -1})

        # 없는 상품 수정은 0행이라 not_found 다
        raises('not_found', product_feat.update_after_select_product, -1, {'price_krw': 1})

        # 위 세 개 중 하나라도 돌았으면 값이 바뀌어 있다
        assert product_feat.get_product(product_id)['price_krw'] == 2000

    finally:
        # features 의 delete_product 는 아직 주석 처리돼 있어 repositories 로 직접 지운다.
        # 남기면 다음 실행의 페이지 조회가 한 칸씩 밀린다
        if product_id is not None:
            assert product_repo.delete(product_id) == 1
            assert product_repo.find_by_id(product_id) is None
    logger.info('#' * 20)

    # ------------------------------------------------------------------ 5
    logger.info('5. searching - 벡터 검색 + 상품 조인 (모델을 올려서 느리다)')

    hits = timed('candidates(프로필, 자연어, limit=5)',
                 lambda: searching.candidates(prof, '털이 부드러워졌어요', limit=5))
    assert hits, '후보가 하나도 안 나왔다'
    # LLM 에 넘길 모양이 맞는지. 키가 빠지면 프롬프트가 조용히 비어서 나간다
    need = {'product_id', 'name', 'brand', 'price_krw', 'score', 'review'}
    assert all(need == set(h) for h in hits), hits[0].keys()
    for h in hits[:3]:
        logger.info(f'\t{h["product_id"]:>4} {h["name"]} {h["price_krw"]}원 score={h["score"]:.4f}')

    # 점수는 내림차순이어야 한다. 뒤집히면 LLM 이 덜 비슷한 걸 먼저 본다
    scores = [h['score'] for h in hits]
    assert scores == sorted(scores, reverse=True), scores
    logger.info('#' * 20)

    # ------------------------------------------------------------------ 6
    logger.info('6. 여기까지 실제 DB 는 그대로여야 한다')
    after = fetch_tuple_one('SELECT count(*), sum(price_krw) FROM product')
    assert after == before, f'DB 가 바뀌었다: {before} -> {after}'
    logger.info(f'\t{before[0]}행 / 합계 {before[1]} 그대로')
    logger.info('#' * 20)

    logger.info('ok')
