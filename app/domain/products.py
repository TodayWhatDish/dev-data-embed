"""product 도메인 마스터 캐시 + 그 캐시로 하는 가공.

분류 트리를 아는 건 여기(캐시)뿐이라, 트리를 걸어야 하는 판정도 여기서 한다.
"""

# 최상위 분류 id -> 화면·프롬프트가 쓰는 이름. 여기 없는 루트가 생기면 그 루트 이름을 그대로 쓴다
ROOT_TYPES = {1: '사료', 2: '간식'}


def root_category_name(product_category_id: int) -> str | None:
    """
    # Summary
    * 상품분류를 최상위까지 올려 사료/간식 중 하나로 접는다. 모르는 분류면 None
    * 트리가 '간식 > 덴탈껌' 처럼 더 나뉘어도 화면은 둘로만 보기 때문
    # params
    * product_category_id: product.product_category_id
    """
    # 예전엔 SQL 의 COALESCE(parent_id, product_category_id) = 1 이 이 일을 했다.
    # 한 단계만 올라가므로 트리가 3단계가 되면 조용히 틀린 값을 준다 - 그래서 끝까지 올린다
    mgr = ProductMgr.get_inst()
    node = mgr.get_product_category(product_category_id)
    seen = set()
    while node and node.get('parent_id') is not None:
        if node['product_category_id'] in seen:
            # 부모가 순환하면 여기서 영영 못 나온다. DB 가 못 막는 규칙이라 앱이 본다 (docs/docu.md)
            return None
        seen.add(node['product_category_id'])
        node = mgr.get_product_category(node['parent_id'])
    if not node:
        return None
    return ROOT_TYPES.get(node['product_category_id'], node['name_ko'])


def attach_product_type(rows: list[dict]) -> list[dict]:
    """구매이력 행에 product_type(사료/간식)을 붙인다. 원본은 안 고친다"""
    return [{**row, 'product_type': root_category_name(row['product_category_id'])}
            for row in rows]


class ProductMgr:
    _instance = None
    def __init__(self):
        pass

    def set_product_category(self, rows: list[dict]):
        """
        # Summary
        * product_category 테이블을 SELECT한 결과를 메모리에 저장
        * allergen 처럼 parent_id 로 자기 자신을 가리키기 때문에 계층형으로 저장
        # info
        * k: product_category_id
        * v: product_category_info, children
        """

        # product_category_id를 키로 가지는 카테고리 정보, 하위 카테고리를 가지는 dict 생성
        nodes = {row['product_category_id']: {**row, 'children': []} for row in rows}

        # 최상위 카테고리는 부모가 없기 때문에 roots로 따로 저장
        roots = []

        for node in nodes.values():
            parent = nodes.get(node['parent_id'])
            if parent: # 부모가 있다면, 부모의 자식으로 노드를 저장
                parent['children'].append(node)
            else: # 부모가 없다면, roots에 저장
                roots.append(node)

        # product_category_id 로 인덱싱 가능
        self._product_category_hierarchy = nodes # 카테고리 정보 트리
        self._product_category_roots = roots # 루트 노드들

    def get_all_product_category_hierarchy(self):
        """
        # Summary
        상품 카테고리 계층 구조 트리 전체를 반환
        """
        return self._product_category_hierarchy

    def get_product_category(self, product_category_id: int | None = None):
        """
        # Summary
        * product_category_id = id -> 해당 카테고리 정보와 하위 카테고리 정보
        * product_category_id = None -> root 노드들 (전체 최상위 정보)
        """

        if not product_category_id:
            return self._product_category_roots

        return self._product_category_hierarchy.get(product_category_id)

    def set_feeding_purpose(self, rows: list[dict]):
        """
        # Summary
        * feeding_purpose 테이블을 SELECT한 결과를 메모리에 저장
        # info
        * k: feeding_purpose_id
        * v: feeding_purpose_info
        """
        self._feeding_purpose = {row['feeding_purpose_id']: row for row in rows}

    def get_feeding_purpose(self, feeding_purpose_id: int | None = None):
        """
        # Summary
        * feeding_purpose_id = id -> 해당 급여목적 정보
        * feeding_purpose_id = None -> {id: 급여목적 정보} 전체
        """

        if not feeding_purpose_id:
            return self._feeding_purpose

        return self._feeding_purpose.get(feeding_purpose_id)

    def set_ingredient(self, rows: list[dict]):
        """
        # Summary
        * ingredient 테이블을 SELECT한 결과를 메모리에 저장
        * 상품이 늘면 원료가 새로 생기는 테이블이다. 원료를 INSERT 했으면 이 캐시를 다시 채워야 한다.
        # info
        * k: ingredient_id
        * v: ingredient_info
        """
        self._ingredient = {row['ingredient_id']: row for row in rows}

    def get_ingredient(self, ingredient_id: int | None = None):
        """
        # Summary
        * ingredient_id = id -> 해당 원료 정보
        * ingredient_id = None -> {id: 원료 정보} 전체
        """

        if not ingredient_id:
            return self._ingredient

        return self._ingredient.get(ingredient_id)

    def set_ingredient_allergen(self, pairs: list[dict]):
        """
        # Summary
        * ingredient_allergen 테이블을 SELECT한 결과를 메모리에 저장
        * 원료 하나가 알러지원 여러 개를 가리키므로 원료 id 로 묶는다
        * 알러지 판정(safty.judge)이 원료마다 이 조회를 해서, 조인 대신 캐시로 들고 있는다
        # info
        * k: ingredient_id
        * v: [allergen_id, ...]
        """
        mapping = {}
        for row in pairs:
            mapping.setdefault(row['ingredient_id'], []).append(row['allergen_id'])

        self._ingredient_allergen = mapping

    def get_ingredient_allergen(self, ingredient_id: int | None = None):
        """
        # Summary
        * ingredient_id = id -> 그 원료가 가진 알러지원 id 목록 (알러지원이 없으면 빈 목록)
        * ingredient_id = None -> {원료 id: [알러지원 id]} 전체
        """

        if not ingredient_id:
            return self._ingredient_allergen

        return self._ingredient_allergen.get(ingredient_id, [])

    @classmethod
    def get_inst(cls): #싱글턴 패턴을 위한
        if cls._instance == None:
            cls._instance = ProductMgr()
        return cls._instance



