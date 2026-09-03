# Last updated: 2026-09-03
# Last Updated : 2026-09-01

"""user 테이블에 연결되는 곳. 관리자 화면용 고객 조회."""

from app.core.db import fetch, fetch_one
from app.repositories.general_query.insert import insert_query

def find_user_by_email(email: str) -> dict | None:
    """로그인/가입 시 이메일 중복 확인. email 은 UNIQUE라 최대 한 행."""
    return fetch_one("SELECT user_id, password_hash FROM user WHERE email = ?", (email,))


def create_user(email: str, name: str, password_hash: str,
                 phone: str | None = None, region: str | None = None) -> int:
    """local 회원가입. auth_uid는 로컬 계정엔 별도 외부 ID가 없어 email을 그대로 쓴다."""
    values = {"auth_provider": "local", "auth_uid": email, "email": email,
              "password_hash": password_hash, "name": name}
    if phone:
        values["phone"] = phone
    if region:
        values["region"] = region
    return insert_query("user", values)


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

    # product_type: product_category는 "간식" 아래 덴탈껌/트릿/수제간식처럼 한 단계 더 나뉠 수 있어
    # parent_id가 있으면 그 부모(=최상위 카테고리)로 올려서 사료(1)/간식(2) 둘로만 구분한다.
    user["purchases"] = fetch("""
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
