from app.domain.common import CommonMgr
from app.repositories.common import get_animal_categories


if __name__ == '__main__':
    mgr = CommonMgr.get_inst()

    mgr.set_animal_category(get_animal_categories())

    print("전체 축종 - {id: 축종 정보}")
    all_category = mgr.get_animal_category()
    for category_id, category in all_category.items():
        print(f"\t{category_id}: {category['name_ko']} ({category['name_eng']})")
    print("#"*20)

    # 개(1)/고양이(2) 둘만 다룬다 - 축종이 늘면 코드표 INSERT 로 끝나지 않는다 (docs/docu.md §2)
    assert len(all_category) == 2, all_category
    print("id 로 한 건 조회")
    for category_id in (1, 2):
        print(f"\t{category_id} -> {mgr.get_animal_category(category_id)['name_ko']}")
    print("#"*20)

    print("존재하지 않는 축종 id")
    no_category = mgr.get_animal_category(500)
    if not no_category:
        print("None!!!")
    else:
        raise ValueError(no_category)
    print("#"*20)

    print('ok')
