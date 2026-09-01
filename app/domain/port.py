"""
[아직 검수 안된 코드]
domain이 저장소에 요청할 수 있는 기능을 인터페이스로 정의한다.
"""

from typing import Any, Mapping, Protocol, Sequence


# 벡터 저장소가 지켜야 할 약속. kind 는 'chunk' · 'product' · 'customer' · 'review' 중 하나다
class VectorStore(Protocol):
    # 그 항목의 벡터 하나. 없으면 None
    def get_vector(self, kind: str, item_id: str) -> Any: ...

    # 가까운 것 k 개를 [(아이디, 점수), ...] 로. 점수는 클수록 가깝다.
    def search(self, kind: str, query_vector: Any, k: int, *,
               only_ids: Sequence[str] | None = None,
               reverse: bool = False) -> list[tuple[str, float]]: ...

    # 그 항목의 벡터가 있나
    def has(self, kind: str, item_id: str) -> bool: ...

    # 이 상품들에 딸린 조각 벡터의 아이디. 검색을 상품으로 좁힐 때 쓴다.
    def chunk_ids_for_products(self, product_ids: Sequence[str]) -> list[str]: ...

    # 베껴 둔 값을 읽는다. {아이디: {컬럼: 값}}.
    def fetch_payloads(self, kind: str, ids: Sequence[str],
                       columns: Sequence[str]) -> dict[str, dict[str, Any]]: ...

    # 저장된 source_hash 를 {아이디: 해시} 로. 무엇을 다시 만들지 고르는 재료다.
    def hashes(self, kind: str, *,
               ids: Sequence[str] | None = None) -> dict[str, str]: ...

    # 벡터 표를 비우고 새로 만든다. 파이프라인이 전량 적재할 때 쓴다.
    def recreate(self, kind: str, *, dim: int, model: str,
                 payload_columns: Mapping[str, str] | None = None) -> None: ...

    # 벡터를 넣거나 고친다. 증분 임베딩이 이걸 한 건씩 부른다.
    def upsert(self, kind: str, ids: Sequence[str], vectors: Sequence[Sequence[float]],
               *, model: str, hashes: Sequence[str],
               payloads: Mapping[str, Sequence[Any]] | None = None) -> None: ...

    # 벡터를 지운다. 원본에서 없어진 행을 따라 지울 때 쓴다
    def delete(self, kind: str, ids: Sequence[str]) -> None: ...

    # 베껴 둔 값 하나를 고친다. 벡터는 안 건드린다.
    def set_payload(self, kind: str, ids: Sequence[str],
                    column: str, value: Any) -> None: ...


Row = dict[str, Any]


# 상품 표에 닿는 자리. 행을 dict 로 주고받는다
class ProductRepository(Protocol):
    # 뜰 때 한 번 도는 마이그레이션. 요청 경로에서 부르지 않는다
    def ensure_source_column(self) -> None: ...

    # 한 건. 없으면 None
    def find_by_id(self, product_id: str) -> Row | None: ...

    # 목록 한 쪽과 전체 건수. (행 목록, 전체 건수)
    def find_page(self, *, keyword: str | None = None, category: str | None = None,
                  skin_type: str | None = None, page: int = 0, size: int = 20,
                  sort: str = "name", order: str = "asc") -> tuple[list[Row], int]: ...

    # 후보 카드 여럿을 한 번에. 아이디 하나마다 한 번씩 묻지 않는다
    def find_cards(self, product_ids: Sequence[str]) -> list[Row]: ...

    # 임베딩 문장을 만들 재료. 없으면 None
    def find_embedding_source(self, product_id: str) -> Row | None: ...

    # 이름 한 개. 없으면 None
    def find_name(self, product_id: str) -> str | None: ...

    # 다음 상품 번호
    def next_id(self) -> str: ...

    # 새 행을 넣는다. 그 번호를 다른 요청이 먼저 가져갔으면 False.
    def insert(self, product_id: str, values: Mapping[str, Any]) -> bool: ...

    # 준 컬럼만 고친다
    def update(self, product_id: str, fields: Mapping[str, Any]) -> None: ...

    # 한 건을 지운다
    def delete(self, product_id: str) -> None: ...
