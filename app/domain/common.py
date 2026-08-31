
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

    @classmethod
    def get_inst(cls): #싱글턴 패턴을 위한
        if cls._instance == None:
            cls._instance = CommonMgr()
        return cls._instance
