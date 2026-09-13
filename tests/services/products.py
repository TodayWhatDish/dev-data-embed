import logging

from app.app_logger.logger import init_logger
from app.core.db import QueryError, execute
from app.repositories import products as product_repo


def rejects(reason, fn, *args):
    """그 사유로 거절당하는지 본다. 통과했거나 다른 사유면 실패다.

    '실패했다'만 보면 엉뚱한 이유로 막혀도 통과해버린다. reason 까지 봐야 의미가 있다.
    """
    try:
        fn(*args)
    except QueryError as e:
        assert e.reason == reason, f"사유가 다르다: {e.reason} != {reason}"
        return
    raise AssertionError(f"거절당해야 하는데 통과했다: {reason}")


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
    return {
        "product_category_id": product_category_id,
        "brand": "테스트브랜드",
        "name": "__테스트상품__",
        "price_krw": 1000,
        "weight_g": 500,
    }


if __name__ == "__main__":
    init_logger("test_products")

    # 1. 마스터 조회 - 컬럼 이름이 붙은 dict 로 와야 도메인이 그대로 받아 캐시에 넣는다
    categories = product_repo.get_product_categories()
    purposes = product_repo.get_feeding_purposes()
    ingredients = product_repo.get_ingredients()
    logger.info(f"분류 {len(categories)}종, 급여목적 {len(purposes)}종, 원료 {len(ingredients)}종")
    assert categories and purposes and ingredients
    assert "product_category_id" in categories[0], categories[0]

    # 2. 페이지 조회 - 페이지가 겹치면 목록에 같은 상품이 두 번 뜬다
    first = product_repo.find_page(0, 5)
    second = product_repo.find_page(1, 5)
    logger.info(f"0페이지 {[p['product_id'] for p in first]} / 1페이지 {[p['product_id'] for p in second]}")
    assert len(first) == 5, len(first)
    assert not ({p["product_id"] for p in first} & {p["product_id"] for p in second})

    # 3. 없는 id 는 예외가 아니라 None - services 가 이 None 을 보고 404 를 만든다
    assert product_repo.find_by_id(-1) is None

    product_id = None
    try:
        # 4. 등록 - 안 넣은 컬럼은 DB DEFAULT 가 채운다. 그래서 등록 후 다시 SELECT 한다
        product_id = product_repo.insert(make_draft(categories[0]["product_category_id"]))
        created = product_repo.find_by_id(product_id)
        logger.info(
            f"등록 {product_id}: {created['name']} / {created['created_at']} / active={created['is_active']}"
        )
        assert created["is_active"] == 1 and created["created_at"]

        # 5. 등록 거절 - 값이 비었거나, 모델에 없는 컬럼 이름이 섞이면 QueryError
        rejects("no_values", product_repo.insert, {})
        rejects(
            "unknown_column",
            product_repo.insert,
            {**make_draft(categories[0]["product_category_id"]), "no_such_col": 1},
        )

        # 6. 일반 UPDATE - 고친 행 수로 존재 여부를 안다
        assert product_repo.update_product(product_id, {"price_krw": 2000}) == 1
        assert product_repo.find_by_id(product_id)["price_krw"] == 2000

        # 7. 없는 id 는 UPDATE 가 터지지 않는다. 0행을 고치고 조용히 성공한다
        assert product_repo.update_product(-1, {"price_krw": 2000}) == 0

        # 8. 고칠 값이 없으면 막는다. 'SET  WHERE' 라는 깨진 SQL 을 막는 자리다
        rejects("no_values", product_repo.update_product, product_id, {})

        # 9. 관리자 PATCH 는 자유 입력이라, 모델에 없는 컬럼 이름은 SQL 을 만들기 전에 막는다
        rejects("unknown_column", product_repo.update_product, product_id, {"no_such_col": 1})

        # 10. DB 제약 위반은 sqlite3 예외가 아니라 QueryError 로 올라온다.
        #     Pydantic 이 음수를 안 막아서 여기까지 내려오는 값이다
        rejects("constraint_check", product_repo.update_product, product_id, {"price_krw": -1})
        # NOT NULL. 파이썬 None 은 값이라 컬럼에 그대로 실려 나가고 DB 가 잡는다
        rejects("constraint_notnull", product_repo.update_product, product_id, {"name": None})
        # PK 충돌. SQLITE_CONSTRAINT_PRIMARYKEY 도 unique 로 묶는다 (부른 쪽엔 같은 얘기다)
        other_id = next(p["product_id"] for p in first if p["product_id"] != product_id)
        rejects("constraint_unique", product_repo.update_product, product_id, {"product_id": other_id})

        # 위 다섯 개 중 하나라도 돌았으면 값은 2000 그대로다
        assert product_repo.find_by_id(product_id)["price_krw"] == 2000
    finally:
        # 비활성화는 행을 남기므로 조회로 확인한 뒤, 테스트가 만든 행은 SQL 로 지운다
        # - 남으면 다음 실행의 페이지 조회가 밀린다
        if product_id is not None:
            assert product_repo.inactive_product(product_id) == 1
            assert product_repo.find_by_id(product_id)["is_active"] == 0
            assert product_repo.inactive_product(-1) == 0  # 없는 id 는 0행
            execute("DELETE FROM product WHERE product_id = ?", (product_id,), "product")
            assert product_repo.find_by_id(product_id) is None

    logger.info("ok")
