import logging

from app.app_logger.logger import init_logger
from app.domain.common import CommonMgr
from app.domain.product import ProductMgr
from app.domain.embedding_text import build_product_rows, product_text
from app.repositories.common import get_animal_categories
from app.repositories.products import (get_product_categories, get_feeding_purposes, get_ingredients,
                                       get_products, get_product_animal_category_ids,
                                       get_product_feeding_purpose_ids, get_product_ingredient_ids)


logger = logging.getLogger()


if __name__ == '__main__':
    init_logger('test_product_embedding')
    common_mgr = CommonMgr.get_inst()
    common_mgr.set_animal_category(get_animal_categories())

    product_mgr = ProductMgr.get_inst()
    product_mgr.set_product_category(get_product_categories())
    product_mgr.set_feeding_purpose(get_feeding_purposes())
    product_mgr.set_ingredient(get_ingredients())

    def category_of(product_category_id):
        """캐시 트리로 (대분류, 소분류)를 찾는다 - product_category 자기조인 대신"""
        node = product_mgr.get_product_category(product_category_id)
        parent = product_mgr.get_product_category(node["parent_id"]) if node["parent_id"] else None
        if parent:
            return parent["name_ko"], node["name_ko"]
        return node["name_ko"], None

    rows = build_product_rows(
        get_products(),
        get_product_animal_category_ids(),
        get_product_feeding_purpose_ids(),
        get_product_ingredient_ids(),
        animal_category_name=lambda i: common_mgr.get_animal_category(i)["name_ko"],
        feeding_purpose_name=lambda i: product_mgr.get_feeding_purpose(i)["name_ko"],
        ingredient_name=lambda i: product_mgr.get_ingredient(i)["name_ko"],
        category_of=category_of,
    )

    logger.info(f"상품 {len(rows)}건 조립")
    assert len(rows) == len(get_products())
    logger.info("#"*20)

    for row in rows[:3]:
        logger.info(product_text(row))
        logger.info("-"*20)
    logger.info("#"*20)

    # 1:N 이 문장에 다 들어왔는지 - 관계 테이블 행 수와 문장의 항목 수가 맞아야 한다.
    # get_products() 가 is_active = 1 만 가져오므로, 비교 대상도 활성 상품의 원료로 좁힌다.
    active_ids = {r["product_id"] for r in rows}
    ing_cnt = sum(len(r["ingredients"].split(", ")) for r in rows if r["ingredients"])
    want = sum(1 for product_id, _ in get_product_ingredient_ids() if product_id in active_ids)
    logger.info(f"원료 항목 합 {ing_cnt} / 활성 상품의 product_ingredient {want}행 "
          f"(전체 {len(get_product_ingredient_ids())}행 - 비활성 상품 제외)")
    assert ing_cnt == want

    no_animal = [r["product_id"] for r in rows if not r["target_animal_category"]]
    logger.info(f"축종이 비어 아무에게도 안 뜨는 상품(fail-closed): {no_animal}")
    logger.info("#"*20)

    logger.info('ok')
