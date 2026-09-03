"""로그인 회원 본인 구매내역/리뷰 - HTTP도 SQL도 모르고 '본인 것만' 규칙만 안다."""

from app.core.db import QueryError
from app.repositories import products as product_repo
from app.repositories import purchases as purchases_repo
from app.repositories.pet import find_pets_by_user


def my_purchases(user_id: int) -> list[dict]:
    """이 회원의 구매 내역. 리뷰가 있으면 rating/review_body가 같이 채워진다."""
    return purchases_repo.list_by_user(user_id)


def buy(user_id: int, product_id: int, quantity: int = 1) -> int:
    """이 회원의 첫 번째 펫이 상품을 산다 - 구매이력에 남아야 그 자리에서 리뷰를 쓸 수 있다.
    가격은 지금 시점 product.price_krw를 그대로 스냅샷한다. 새로 생긴 purchase_id를 돌려준다."""
    pets = find_pets_by_user(user_id)
    if not pets:
        raise ValueError("등록된 반려동물이 없습니다.")

    product = product_repo.find_by_id(product_id)
    if product is None:
        raise ValueError("존재하지 않는 상품입니다.")

    return purchases_repo.create_purchase(pets[0]["pet_id"], product_id, quantity, product["price_krw"])


def write_review(user_id: int, purchase_id: int, rating: int, body: str) -> None:
    """본인 구매에만 리뷰를 남길 수 있다. 남의 구매거나 이미 리뷰가 있으면 ValueError."""
    if not purchases_repo.is_owned_by(purchase_id, user_id):
        raise ValueError("본인 구매 내역이 아닙니다.")
    try:
        purchases_repo.create_review(purchase_id, rating, body)
    except QueryError as e:
        if e.reason == "constraint_unique":
            raise ValueError("이미 리뷰를 작성했습니다.")
        raise
