import logging

from app.app_logger.logger import init_logger
from app.domain.pet import PetMgr
from app.repositories.pet import get_breeds


logger = logging.getLogger()


if __name__ == '__main__':
    init_logger('test_breed')
    mgr = PetMgr.get_inst()

    mgr.set_breeds(get_breeds())

    logger.info("축종별 품종 - {animal_category_id: [품종...]}")
    all_breeds = mgr.get_all_breeds()
    for category_id, breeds in all_breeds.items():
        logger.info(f"\t{category_id}: {[b['name_ko'] for b in breeds]}")
    logger.info("#"*20)

    # 품종 드롭다운은 축종으로 걸러 채운다 - 개 목록에 고양이 품종이 섞이면 안 된다 (docs/docu.md §1)
    dog_breeds = mgr.get_breeds(1)
    cat_breeds = mgr.get_breeds(2)
    logger.info(f"개 품종 {len(dog_breeds)}종, 고양이 품종 {len(cat_breeds)}종")
    assert dog_breeds and cat_breeds
    assert not (set(b['breed_id'] for b in dog_breeds) & set(b['breed_id'] for b in cat_breeds)) # 교집합 체크
    assert len(dog_breeds) + len(cat_breeds) == len(get_breeds())
    logger.info("#"*20)

    logger.info("존재하지 않는 축종 id")
    no_breeds = mgr.get_breeds(500)
    if not no_breeds:
        logger.info("[] !!!") # KeyError 로 터지지 않고 빈 목록이어야 한다
    else:
        raise ValueError(no_breeds)
    logger.info("#"*20)

    logger.info('ok')
