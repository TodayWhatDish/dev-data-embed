"""고객 상세를 조립하는 자리. repositories 가 읽고 domain 이 가공하는 순서를 여기서 엮는다.

get_user_detail() 을 라우트가 직접 부르던 걸 여기로 모았다. 구매이력의 사료/간식 구분처럼
**마스터 캐시를 봐야 아는 값**이 붙는 곳이 한 군데여야, 새 호출자가 그걸 빠뜨리지 않는다.
"""

import logging

from app.domain import products as product_domain
from app.repositories import users as users_repo

logger = logging.getLogger()


def customer_detail(user_id: int) -> dict | None:
    """고객 프로필 + 반려동물 + 구매이력. 없는 고객은 예외가 아니라 None."""
    detail = users_repo.get_user_detail(user_id)
    if detail is None:
        logger.info(f"user_id={user_id} 가 없다")
        return None

    # repo 는 product_category_id 까지만 준다. 사료/간식으로 접는 건 분류 트리를 걸어야 하는
    # 일이라 캐시를 가진 domain 이 한다 (docs/WORK.md 2026-09-03 §11)
    detail["purchases"] = product_domain.attach_product_type(detail["purchases"])
    return detail
