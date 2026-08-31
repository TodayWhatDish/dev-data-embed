
class CommonMgr:
    _instance = None
    def __init__(self):
        pass

    def set_allergen_info(self, rows: list[dict]):
        """
        # Summary
        * allergen 테이블을 SELECT한 결과를 메모리에 저장
        * rows입력은 allegen_id - parent_id가 정렬되어 있어야 합니다.
        # info
        * k: allergen_id
        * v: allegen_info, child_allergen
        """

        # allregen_id를 키로 가지는 알러지 정보, 자식 알러지를 가지는 dict 생성
        nodes = {row['allergen_id']: {**row, 'children': []} for row in rows}

        # 최상위 알러지는 부모가 없기 때문에 roots로 따로 저장
        roots = []

        for node in nodes.values():
            parent = nodes.get(node['parent_id'])
            if parent: # 순회하면서, 노드의 부모가 있다면, 부모의 자식으로 노드를 저장
                parent['children'].append(node)
            else: # 부모가 없다면, roots에 저장
                roots.append(node)

        # allerge_id 로 인덱싱 가능
        self._allergen_hierarchy = nodes #알러지 정보 트리
        self._allergen_roots = roots # 루트 노드들

    def get_all_allergen_hierarchy(self):
        """
        # summary
        알러지 계층 구조 트리 전체를 반환
        """
        return self._allergen_hierarchy

    def get_allergen(self, allergen_id: int | None = None):
        """
        # Summary
        * allergen_id에 맞는 알러지 정보와 하위 알러지 정보를 반환
        * k: allergen_id, v: allergen_info, child(하위 알러지 정보)

        # params
        * allergen_id = id
            * 필요한 알러지의 id
        * allergen_id = None
            * 전체 알러지 정보가 필요한 경우
            * root 노드들을 리턴하여 전체 알러지 최상위 정보를 리턴
        """

        if not allergen_id:
            return self._allergen_roots

        return self._allergen_hierarchy.get(allergen_id)

    def get_allergen_names(self) -> list[str]:
        """
        # Summary
        * 등록된 알러지원 이름(name_ko) 전체를 반환
        * 자유 텍스트에서 알러지 이름을 찾을 때 사용 (features/profile.py)
        """
        return [node['name_ko'] for node in self._allergen_hierarchy.values()]

    def set_animal_category(self, rows: list[dict]):
        """
        # Summary
        * animal_category 테이블을 SELECT한 결과를 메모리에 저장
        # info
        * k: animal_category_id
        * v: animal_category_info
        """
        self._animal_category = {row['animal_category_id']: row for row in rows}

    def get_animal_category(self, animal_category_id: int | None = None):
        """
        # Summary
        * animal_category_id = id -> 해당 축종 정보
        * animal_category_id = None -> {id: 축종 정보} 전체
        """
        if not animal_category_id:
            return self._animal_category

        return self._animal_category.get(animal_category_id)

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

    @classmethod
    def get_inst(cls): #싱글턴 패턴을 위한
        if cls._instance == None:
            cls._instance = CommonMgr()
        return cls._instance
