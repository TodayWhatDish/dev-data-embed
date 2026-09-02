import logging

from app.app_logger.logger import init_logger
from app.repositories import products as product_repo
from app.repositories.general_query import update_query, update_query_all

logger = logging.getLogger()


def make_draft(product_category_id: int) -> dict:
    """
    # Summary
    * 테스트용 상품 한 건의 INSERT 값을 만든다
    * NOT NULL 이면서 DEFAULT 가 없는 컬럼만 채운다 — 나머지를 비워야
      DB 가 채우는 값(created_at, is_active)이 실제로 오는지 볼 수 있다
    # params
    * product_category_id: 실재하는 분류 id. FK RESTRICT 라 아무 숫자나 넣으면 INSERT 가 막힌다
    """
    return {'product_category_id': product_category_id,
            'brand': '테스트브랜드', 'name': '__테스트상품__',
            'price_krw': 1000, 'weight_g': 500}


if __name__ == '__main__':
    init_logger('test_products')

    # 1. 마스터 조회 - 컬럼 이름이 붙은 dict 로 와야 도메인이 그대로 받아 캐시에 넣는다
    categories = product_repo.get_product_categories()
    purposes = product_repo.get_feeding_purposes()
    ingredients = product_repo.get_ingredients()
    logger.info(f'분류 {len(categories)}종, 급여목적 {len(purposes)}종, 원료 {len(ingredients)}종')
    assert categories and purposes and ingredients
    assert 'product_category_id' in categories[0], categories[0]

    # 2. 페이지 조회 - 페이지가 겹치면 목록에 같은 상품이 두 번 뜬다
    first = product_repo.find_page(0, 5)
    second = product_repo.find_page(1, 5)
    logger.info(f'0페이지 {[p["product_id"] for p in first]} / 1페이지 {[p["product_id"] for p in second]}')
    assert len(first) == 5, len(first)
    assert not ({p['product_id'] for p in first} & {p['product_id'] for p in second})

    # 3. 없는 id 는 예외가 아니라 None - features 가 이 None 을 보고 404 를 만든다
    assert product_repo.find_by_id(-1) is None

    # 4. 전체 UPDATE 는 확인 인자가 없으면 수행되지 않는다
    #    실수로 부르면 테이블이 통째로 덮이는 쿼리라, 여기서만은 '안 도는 것'을 확인한다
    assert update_query_all('product', {'is_active': 0}) == -1

    product_id = None
    try:
        # 5. 등록 - 안 넣은 컬럼은 DB DEFAULT 가 채운다. 그래서 등록 후 다시 SELECT 한다
        product_id = product_repo.insert(make_draft(categories[0]['product_category_id']))
        created = product_repo.find_by_id(product_id)
        logger.info(f'등록 {product_id}: {created["name"]} / {created["created_at"]} / active={created["is_active"]}')
        assert created['is_active'] == 1 and created['created_at']

        # 6. 일반화 UPDATE - 고친 행 수로 존재 여부를 안다
        assert update_query('product', {'price_krw': 2000}, {'product_id': product_id}) == 1
        assert product_repo.find_by_id(product_id)['price_krw'] == 2000

        # 7. 없는 id 는 UPDATE 가 터지지 않는다. 0행을 고치고 조용히 성공한다
        assert update_query('product', {'price_krw': 2000}, {'product_id': -1}) == 0

        # 8. 고칠 값이 없으면 쿼리를 만들지 않고 -1. 'SET  WHERE' 라는 깨진 SQL 을 막는 자리다
        assert update_query('product', {}, {'product_id': product_id}) == -1

    finally:
        # 9. 테스트가 만든 행은 반드시 지운다 - 남으면 다음 실행의 페이지 조회가 밀린다
        if product_id is not None:
            assert product_repo.delete(product_id) == 1
            assert product_repo.delete(product_id) == 0   # 두 번째는 지울 게 없어 0
            assert product_repo.find_by_id(product_id) is None

    logger.info('ok')
