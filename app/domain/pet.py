
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
