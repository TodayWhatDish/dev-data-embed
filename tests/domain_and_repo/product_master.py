import logging

from app.app_logger.logger import init_logger
from app.domain.products import ProductMgr
from app.repositories.products import get_product_categories, get_feeding_purposes, get_ingredients


def print_category_child(child, parent_category: str | None = None, tab_cnt = 0):
    """
    # summary
    재귀 함수를 통해, 하위 카테고리를 순회하고 전부 출력
    """
    if parent_category:
        logger.info("\t"*tab_cnt + f"{parent_category}")

    for c in child:
        print_category_child(c["children"], c["name_ko"], tab_cnt+1)


logger = logging.getLogger()


if __name__ == '__main__':
    init_logger('test_product_master')
    mgr = ProductMgr.get_inst()

    mgr.set_product_category(get_product_categories())
    mgr.set_feeding_purpose(get_feeding_purposes())
    mgr.set_ingredient(get_ingredients())

    logger.info("상품 카테고리 계층")
    root = mgr.get_product_category()
    for r in root:
        print_category_child(r["children"], r["name_ko"], 0)
    logger.info("#"*20)

    # 트리가 제대로 이어졌는지 - 루트 + 모든 자식의 합이 전체 행 수와 같아야 한다
    hierarchy = mgr.get_all_product_category_hierarchy()
    assert len(hierarchy) == len(get_product_categories())
    assert len(root) + sum(len(node["children"]) for node in hierarchy.values()) == len(hierarchy)
    logger.info(f"루트 {len(root)}개 / 전체 {len(hierarchy)}개")
    logger.info("#"*20)

    logger.info("id 로 한 건 조회 - 하위 카테고리까지")
    for category_id in list(hierarchy)[:3]:
        category = mgr.get_product_category(category_id)
        logger.info(f"\t{category_id}: {category['name_ko']} <- 하위 {[c['name_ko'] for c in category['children']]}")
    logger.info("#"*20)

    logger.info("급여 목적 - {id: 급여목적 정보}")
    for purpose_id, purpose in mgr.get_feeding_purpose().items():
        logger.info(f"\t{purpose_id}: {purpose['name_ko']}")
    assert len(mgr.get_feeding_purpose()) == len(get_feeding_purposes())
    logger.info("#"*20)

    logger.info("원료 - {id: 원료 정보}")
    ingredients = mgr.get_ingredient()
    logger.info(f"\t{len(ingredients)}종: {[i['name_ko'] for i in list(ingredients.values())[:5]]} ...")
    assert len(ingredients) == len(get_ingredients())
    logger.info("#"*20)

    logger.info("존재하지 않는 id")
    for name, value in (("product_category", mgr.get_product_category(500)),
                        ("feeding_purpose",  mgr.get_feeding_purpose(500)),
                        ("ingredient",       mgr.get_ingredient(500))):
        if value:
            raise ValueError((name, value))
        logger.info(f"\t{name} -> None!!!")
    logger.info("#"*20)

    logger.info('ok')

    # 사료/간식 접기 - 예전 SQL 의 COALESCE(parent_id, product_category_id) = 1 과 답이 같아야 한다.
    # 그 CASE 가 web/admin.js 의 필터 값이라 '사료'/'간식' 글자가 바뀌면 화면이 빈다
    from app.domain.products import attach_product_type, root_category_name
    from app.repositories.general_query import select_all
    for row in select_all('product_category'):
        cid, parent = row['product_category_id'], row['parent_id']
        before = '사료' if (parent or cid) == 1 else '간식'
        assert root_category_name(cid) == before, f"{row['name_ko']}({cid}) != {before}"
    assert root_category_name(-1) is None, '모르는 분류는 None 이다'

    # 행에 붙이는 쪽. 원본을 안 고쳐야 한다 (부르는 쪽이 또 쓸 수 있어서)
    rows = [{'product_category_id': 3}, {'product_category_id': 1}]
    assert [r['product_type'] for r in attach_product_type(rows)] == ['간식', '사료']
    assert 'product_type' not in rows[0], '원본이 오염됐다'
    logger.info('상품분류 트리 접기 ok')
