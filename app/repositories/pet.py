# Last Updated : 2026-09-02

"""pet 테이블과 그 주변(animal_category, pet_allergy)에 닿는 자리.

조회가 전부 JOIN 이라 general_query 를 쓰지 않는다. general_query 는 테이블·컬럼 이름을
바깥에서 받아 SQL 을 만들 때 필요한 물건이고, 여기는 이름이 코드에 글자로 박혀 있어
화이트리스트로 걸러야 할 대상이 애초에 없다. 대신 조인 모양을 여기 가둬둔다 —
features 가 테이블 이름을 알면 스키마가 바뀔 때 고칠 곳이 흩어진다.
"""

import logging
import sqlite3

from app.core.db import fetch, fetch_tuples, fetch_tuple_one
from app.repositories.general_query import select_all

logger = logging.getLogger()


def get_breeds():
    # 테이블 하나를 통째로 읽는 거라 general_query 로 간다. 아래 조인들과 갈리는 지점이다
    return select_all("breed")

def find_pets_by_user(user_id: int) -> list[dict]:
    """한 사용자의 (비활성 아닌) 펫 목록. 알레르기는 이름을 콤마로 이어 한 칸에 담아 준다.

    알레르기를 상관 서브쿼리로 뽑는 이유는 pet_allergy 가 다대다여서다. 조인으로 펼치면
    알레르기 수만큼 펫이 중복되고, 부르는 쪽이 다시 묶어야 한다.
    """
    try:
        return fetch("""
            SELECT p.pet_id, p.name, ac.name_ko AS animal_category, p.size,
                   (SELECT GROUP_CONCAT(al.name_ko)
                      FROM pet_allergy AS pa
                      JOIN allergen AS al ON al.allergen_id = pa.allergen_id
                     WHERE pa.pet_id = p.pet_id) AS allergies
              FROM pet AS p
              JOIN animal_category AS ac ON ac.animal_category_id = p.animal_category_id
             WHERE p.user_id = ? AND p.inactive_at IS NULL
             ORDER BY p.pet_id
        """, (user_id,))
    except sqlite3.Error:
        # SQL 에 글자로 박힌 오타나 스키마 변경은 우리 버그다. 어느 쿼리였는지만 남기고 그대로 올린다
        logger.exception(f"pet 목록 조회 실패: user_id={user_id}")
        raise

def find_category_and_size(pet_id: int) -> tuple | None:
    """펫 한 마리의 (축종 이름, 체급 코드). 없으면 None.

    '없는 id 는 예외가 아니라 None' 이 이 프로젝트의 조회 규약이라 여기서도 그대로 따른다.
    """
    try:
        return fetch_tuple_one("""
            SELECT ac.name_ko AS animal_category, p.size
              FROM pet AS p
              JOIN animal_category AS ac ON ac.animal_category_id = p.animal_category_id
             WHERE p.pet_id = ?
        """, (pet_id,))
    except sqlite3.Error:
        logger.exception(f"pet 조회 실패: pet_id={pet_id}")
        raise

def find_allergen_names(pet_id: int) -> list[str]:
    """그 펫에게 등록된 알레르겐 이름들. 없으면 빈 목록."""
    try:
        rows = fetch_tuples(
            "SELECT al.name_ko FROM pet_allergy AS pa "
            "JOIN allergen AS al ON al.allergen_id = pa.allergen_id WHERE pa.pet_id = ?",
            (pet_id,),
        )
    except sqlite3.Error:
        logger.exception(f"pet 알레르기 조회 실패: pet_id={pet_id}")
        raise

    # 튜플을 벗겨서 준다. 부르는 쪽마다 [name for (name,) in ...] 을 반복하지 않게
    return [name for (name,) in rows]
