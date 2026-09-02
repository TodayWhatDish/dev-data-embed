# Last Updated : 2026-09-01

"""user 테이블에 연결되는 곳. 관리자 화면용 고객 조회."""

from app.core.db import dicts

def list_users() -> list[dict]:
    """관리자 화면 왼쪽 목록용. 고객 전체를 이름순으로.

    species는 이 고객이 키우는 반려동물 종을 콤마로 합친 값(예: "개,고양이") - 목록에서
    강아지/고양이/모두 카테고리를 나누는 데 쓴다. gender/birth_date는 첫 번째로 등록된
    반려동물의 것이다 (사람 성별·나이가 아니다 - user 테이블엔 그 둘이 없다).
    """
    return dicts("""
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
    rows = dicts("""
        SELECT user_id, name, email, phone, region, created_at, last_login_at
        FROM user WHERE user_id = ?
    """, (user_id,))
    if not rows:
        return None
    user = rows[0]

    user["pets"] = dicts("""
        SELECT pe.pet_id, pe.name, ac.name_ko AS animal_category, pe.gender, pe.birth_date, pe.weight_kg, pe.neutered
        FROM pet AS pe
        JOIN animal_category AS ac ON ac.animal_category_id = pe.animal_category_id
        WHERE pe.user_id = ?
    """, (user_id,))

    # product_type: product_category는 "간식" 아래 덴탈껌/트릿/수제간식처럼 한 단계 더 나뉠 수 있어
    # parent_id가 있으면 그 부모(=최상위 카테고리)로 올려서 사료(1)/간식(2) 둘로만 구분한다.
    user["purchases"] = dicts("""
        SELECT pu.purchase_id, pu.purchased_at, pu.unit_price_krw, pu.quantity,
               p.product_id, p.name AS product_name, r.rating, r.body AS review_body,
               CASE WHEN COALESCE(pc.parent_id, pc.product_category_id) = 1 THEN '사료' ELSE '간식' END AS product_type
        FROM purchase AS pu
        JOIN pet AS pe ON pe.pet_id = pu.pet_id
        JOIN product AS p ON p.product_id = pu.product_id
        JOIN product_category AS pc ON pc.product_category_id = p.product_category_id
        LEFT JOIN review AS r ON r.purchase_id = pu.purchase_id
        WHERE pe.user_id = ?
        ORDER BY pu.purchased_at DESC
    """, (user_id,))

    return user
