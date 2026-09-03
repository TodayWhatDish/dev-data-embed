# Last Updated : 2026-09-01

"""user 테이블에 연결되는 곳. 관리자 화면용 고객 조회."""

from app.core.db import fetch, fetch_one

def list_users() -> list[dict]:
    """관리자 화면 왼쪽 목록용. 고객 전체를 이름순으로.

    # return fetch("""
    #     SELECT user_id, name, email, region, created_at
    #     FROM user
    #     ORDER BY name
    # """)

    """
    species는 이 고객이 키우는 반려동물 종을 콤마로 합친 값(예: "개,고양이") - 목록에서
    강아지/고양이/모두 카테고리를 나누는 데 쓴다. gender/birth_date는 첫 번째로 등록된
    반려동물의 것이다 (사람 성별·나이가 아니다 - user 테이블엔 그 둘이 없다).
    """
    return fetch("""
        SELECT u.user_id, u.name, u.email, u.region, u.created_at,
               (SELECT GROUP_CONCAT(DISTINCT ac.name_ko)
                  FROM pet AS pe
                  JOIN animal_category AS ac ON ac.animal_category_id = pe.animal_category_id
                 WHERE pe.user_id = u.user_id) AS species,
               (SELECT pe.gender FROM pet AS pe WHERE pe.user_id = u.user_id ORDER BY pe.pet_id LIMIT 1) AS gender,
               (SELECT pe.birth_date FROM pet AS pe WHERE pe.user_id = u.user_id ORDER BY pe.pet_id LIMIT 1) AS birth_date
        FROM user AS u
        ORDER BY u.name
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
        SELECT pe.pet_id, pe.name, ac.name_ko AS animal_category, pe.gender, pe.birth_date, pe.weight_kg, pe.neutered
        FROM pet AS pe
        JOIN animal_category AS ac ON ac.animal_category_id = pe.animal_category_id
        WHERE pe.user_id = ?
    """, (user_id,))

    # product_category_id 를 그대로 준다. 사료/간식으로 접는 건 분류 트리를 걸어야 하는 일이고,
    # 트리를 들고 있는 건 ProductMgr 캐시다 - domain.products.attach_product_type 이 붙인다
    user["purchases"] = fetch("""
        SELECT pu.purchase_id, pu.purchased_at, pu.unit_price_krw, pu.quantity,
               p.product_id, p.name AS product_name, r.rating, r.body AS review_body,
               p.product_category_id
        FROM purchase AS pu
        JOIN pet AS pe ON pe.pet_id = pu.pet_id
        JOIN product AS p ON p.product_id = pu.product_id
        LEFT JOIN review AS r ON r.purchase_id = pu.purchase_id
        WHERE pe.user_id = ?
        ORDER BY pu.purchased_at DESC
    """, (user_id,))

    return user
