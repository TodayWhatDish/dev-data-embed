# Last Updated : 2026-09-26

"""벡터 저장소가 지켜야 할 약속(Protocol). 구현은 adapters/vector_store.py 의 PgVectorStore."""

from typing import Protocol, Sequence


# 벡터 저장소가 지켜야 할 약속. kind 는 지금 'chunk' 하나뿐이다.
class VectorStore(Protocol):
    # 저장된 source_hash 를 {아이디: 해시} 로. 무엇을 다시 만들지 고르는 재료다.
    def hashes(self, kind: str, *, ids: Sequence[str] | None = None) -> dict[str, str]: ...

    # 벡터 표를 비우고 새로 만든다. 최초 1회와 --full 에서만 부른다.
    def recreate(self, kind: str, *, dim: int, model: str) -> None: ...

    # 벡터를 넣거나 갈아 끼운다. 증분 임베딩의 본작업이다.
    def upsert(
        self,
        kind: str,
        ids: Sequence[str],
        vectors: Sequence[Sequence[float]],
        *,
        model: str,
        hashes: Sequence[str],
    ) -> None: ...

    # 원본에서 없어진 조각의 벡터를 지운다.
    def delete(self, kind: str, ids: Sequence[str]) -> None: ...

