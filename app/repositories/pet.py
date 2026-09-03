# Last updated: 2026-09-03
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
from app.repositories.general_query.insert import insert_query

logger = logging.getLogger()


def create_pet(user_id: int, animal_category_id: int, name: str, gender: str = None,
               birth_date: str = None, weight_kg: float = None,
               size: int = None, body_type: int = None) -> int:
    """반려동물 등록. 값이 없는 선택 컬럼은 뺀다 - insert_query가 남은 컬럼은 NULL로 채운다."""
    values = {"user_id": user_id, "animal_category_id": animal_category_id, "name": name}
    for k, v in (("gender", gender), ("birth_date", birth_date), ("weight_kg", weight_kg),
                 ("size", size), ("body_type", body_type)):
        if v is not None:
            values[k] = v
    return insert_query("pet", values)


def get_breeds():
    # 테이블 하나를 통째로 읽는 거라 general_query 로 간다. 아래 조인들과 갈리는 지점이다
    return select_all("breed")

def find_pets_by_user(user_id: int) -> list[dict]:
    """한 사용자의 (비활성 아닌) 펫 목록. **마스터 이름은 안 붙인다** - id 로만 준다.

    축종/알레르겐은 기동 때 메모리에 올라간 마스터라 조인할 이유가 없다. 이름 붙이기는
    domain.pet.attach_names() 가 캐시로 한다 (docs/WORK.md 2026-09-03 §10).
    쿼리는 그래도 한 방이다 - 관계를 두 번 나눠 읽으면 문장 수가 늘어 그게 더 비싸다.

    알레르겐을 상관 서브쿼리로 뽑는 이유는 pet_allergy 가 다대다여서다. 조인으로 펼치면
    알레르기 수만큼 펫이 중복되고, 부르는 쪽이 다시 묶어야 한다.
    """
    return _fetch_pets('p.user_id = ? AND p.inactive_at IS NULL', (user_id,),
                       f'user_id={user_id}')

def find_pet(pet_id: int) -> dict | None:
    """펫 한 마리. 없으면 None ('없는 id 는 예외가 아니라 None' 이 이 프로젝트의 조회 규약).

    find_pets_by_user 와 **같은 모양**을 준다. 그래야 attach_names() 하나가 둘 다 받는다.
    여기는 inactive_at 을 안 본다 - 비활성 펫도 상세는 열려야 한다.
    """
    rows = _fetch_pets('p.pet_id = ?', (pet_id,), f'pet_id={pet_id}')
    return rows[0] if rows else None

def _fetch_pets(where: str, params: tuple, what: str) -> list[dict]:
    """펫 조회 한 모양. where 는 **코드에 글자로 박힌 것만** 넘긴다 - 사용자 입력은 params 로만 간다"""
    try:
        return fetch(f"""
            SELECT p.pet_id, p.name, p.animal_category_id, p.size,
                   (SELECT GROUP_CONCAT(pa.allergen_id)
                      FROM pet_allergy AS pa
                     WHERE pa.pet_id = p.pet_id) AS allergen_ids
              FROM pet AS p
             WHERE {where}
             ORDER BY p.pet_id
        """, params)
    except sqlite3.Error:
        # SQL 에 글자로 박힌 오타나 스키마 변경은 우리 버그다. 어느 조회였는지만 남기고 그대로 올린다
        logger.exception(f"pet 조회 실패: {what}")
        raise
