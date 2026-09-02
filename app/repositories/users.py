# Last Updated : 2026-09-01

"""user 테이블에 연결되는 곳. 관리자 화면용 고객 조회."""

from app.core.db import fetch, fetch_one

def list_users() -> list[dict]:
    """관리자 화면 왼쪽 목록용. 고객 전체를 이름순으로."""
    return fetch("""
        SELECT user_id, name, email, region, created_at
        FROM user
        ORDER BY name
    """)


def get_user_detail(user_id: int) -> dict | None:
    """고객 한 명의 프로필 + 반려동물 + 구매이력을 한 번에 묶는다."""
    user = fetch_one("""
        SELECT user_id, name, email, phone, region, created_at, last_login_at
        FROM user WHERE user_id = ?
    """, (user_id,))
    if not user:
        return None

    user["pets"] = fetch("""
        SELECT pe.pet_id, pe.name, ac.name_ko AS animal_category, pe.weight_kg, pe.neutered
        FROM pet AS pe
        JOIN animal_category AS ac ON ac.animal_category_id = pe.animal_category_id
        WHERE pe.user_id = ?
    """, (user_id,))

    user["purchases"] = fetch("""
        SELECT pu.purchase_id, pu.purchased_at, pu.unit_price_krw, pu.quantity,
               p.product_id, p.name AS product_name, r.rating, r.body AS review_body
        FROM purchase AS pu
        JOIN pet AS pe ON pe.pet_id = pu.pet_id
        JOIN product AS p ON p.product_id = pu.product_id
        LEFT JOIN review AS r ON r.purchase_id = pu.purchase_id
        WHERE pe.user_id = ?
        ORDER BY pu.purchased_at DESC
    """, (user_id,))

    return user
