"""
[아직 검수 안된 코드]
domain이 저장소에 요청할 수 있는 기능을 인터페이스로 정의한다.
"""

from typing import Any, Mapping, Protocol, Sequence


# 벡터 저장소가 지켜야 할 약속. kind 는 지금 'chunk' 하나뿐이다.
class VectorStore(Protocol):
    # 저장된 source_hash 를 {아이디: 해시} 로. 무엇을 다시 만들지 고르는 재료다.
    def hashes(self, kind: str, *,
               ids: Sequence[str] | None = None) -> dict[str, str]: ...

    # 벡터 표를 비우고 새로 만든다. 최초 1회와 --full 에서만 부른다.
    def recreate(self, kind: str, *, dim: int, model: str) -> None: ...

    # 벡터를 넣거나 갈아 끼운다. 증분 임베딩의 본작업이다.
    def upsert(self, kind: str, ids: Sequence[str], vectors: Sequence[Sequence[float]],
               *, model: str, hashes: Sequence[str]) -> None: ...

    # 원본에서 없어진 조각의 벡터를 지운다.
    def delete(self, kind: str, ids: Sequence[str]) -> None: ...



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
