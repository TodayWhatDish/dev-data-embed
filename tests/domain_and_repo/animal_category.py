import logging

from app.app_logger.logger import init_logger
from app.domain.common import CommonMgr
from app.repositories.common import get_animal_categories


logger = logging.getLogger()


if __name__ == '__main__':
    init_logger('test_animal_category')
    mgr = CommonMgr.get_inst()

    mgr.set_animal_category(get_animal_categories())

    logger.info("전체 축종 - {id: 축종 정보}")
    all_category = mgr.get_animal_category()
    for category_id, category in all_category.items():
        logger.info(f"\t{category_id}: {category['name_ko']} ({category['name_eng']})")
    logger.info("#"*20)

    # 개(1)/고양이(2) 둘만 다룬다 - 축종이 늘면 코드표 INSERT 로 끝나지 않는다 (docs/docu.md §2)
    assert len(all_category) == 2, all_category
    logger.info("id 로 한 건 조회")
    for category_id in (1, 2):
        logger.info(f"\t{category_id} -> {mgr.get_animal_category(category_id)['name_ko']}")
    logger.info("#"*20)

    logger.info("존재하지 않는 축종 id")
    no_category = mgr.get_animal_category(500)
    if not no_category:
        logger.info("None!!!")
    else:
        raise ValueError(no_category)
    logger.info("#"*20)

    logger.info('ok')
