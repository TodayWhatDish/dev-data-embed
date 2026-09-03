"""pet 도메인. 마스터(breed) 캐시와, repositories 가 준 행에 마스터 이름을 붙이는 가공.

**조인은 SQL 이 하고 이름은 여기서 붙인다.** repositories 는 축종/알레르겐을 id 로만 주고
(pet.find_pets_by_user), 그 id 를 이름으로 바꾸는 건 기동 때 올라간 CommonMgr 캐시가 한다.
마스터를 조인하나 캐시에서 찾으나 속도는 같지만(docs/WORK.md 2026-09-03 §2), 이름 붙이는
규칙이 SQL 에 흩어지지 않고 여기 한 곳에 모인다.
"""

from app.domain.common import CommonMgr


def attach_names(rows: list[dict]) -> list[dict]:
    """
    # Summary
    * repositories 가 준 펫 행의 id 를 마스터 캐시로 이름으로 바꾼다
    * 원본을 안 고치고 새 dict 를 만든다 - 부르는 쪽이 원본을 또 쓰는 경우가 있어서
    # info
    * animal_category_id -> animal_category (축종 이름)
    * allergen_ids ('3,7,9' 또는 None) -> allergies (['닭고기', ...])
    # params
    * rows: find_pets_by_user() / find_pet() 이 준 행들. 둘이 같은 모양이라 하나로 받는다
    """
    cmgr = CommonMgr.get_inst()
    out = []
    for row in rows:
        # 마스터에 없는 id 는 이름 대신 None 이다. 여기서 터뜨리면 펫 목록 전체가 안 뜬다 -
        # 화면은 한 칸이 비는 걸로 끝나고, 원인은 마스터 적재 로그에서 찾는 게 맞다
        category = cmgr.get_animal_category(row['animal_category_id'])
        ids = row.get('allergen_ids')
        out.append({**row,
                    'animal_category': category['name_ko'] if category else None,
                    'allergies': [cmgr.get_allergen(int(i))['name_ko']
                                  for i in ids.split(',')] if ids else []})
    return out


def attach_names_one(row: dict | None) -> dict | None:
    """한 행짜리. find_pet() 이 None 을 줄 수 있어 그대로 통과시킨다"""
    return attach_names([row])[0] if row else None


class PetMgr:
    """
    # Summary
    * pet 도메인 마스터(breed) 캐시
    """
    _instance = None
    def __init__(self):
        pass

    def set_breeds(self, rows: list[dict]):
        """
        # Summary
        * breed 테이블을 SELECT한 결과를 축종별로 묶어 메모리에 저장
        * 품종 드롭다운을 animal_category_id 로 걸러 채워야 하기 때문 (docs/docu.md §1)
        # info
        * k: animal_category_id
        * v: [breed_info, ...]
        """
        breeds = {}
        # 동물 축종에 대한 종 정보를 저장
        # ex) 강아지 - [포메, 웰시, 겨울이, 시바견, 진도개...]
        # ex) 고양이 - [먼치킨, 코숏...]
        for row in rows:
            breeds.setdefault(row['animal_category_id'], []).append(row)

        self._breeds = breeds

    def get_breeds(self, animal_category_id: int) -> list[dict]:
        """
        # Summary
        * 해당 축종에 속한 품종 목록을 반환, 없는 축종이면 빈 리스트
        """
        return self._breeds.get(animal_category_id, [])

    def get_all_breeds(self):
        """
        # Summary
        축종별로 묶인 품종 정보 전체를 반환
        # info
        * k: animal_category_id, v: [breed_info, ...]
        """
        return self._breeds

    @classmethod
    def get_inst(cls): #싱글턴 패턴을 위한
        if cls._instance == None:
            cls._instance = PetMgr()
        return cls._instance
