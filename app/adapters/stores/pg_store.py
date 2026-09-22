# Postgres(pgvector) 어댑터. SqliteVectorStore를 대체한다 - 계약(port.py의 VectorStore)은 그대로.

from sqlalchemy import delete, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import ProgrammingError

from app.core.db import Base

# kind -> (벡터 테이블, 원본 테이블). 지금은 chunk 하나뿐이다.
TABLES = {"chunk": ("chunk_vectors", "chunks")}


def chunk_id(purchase_id: int, chunk_index: int) -> str:
    """chunk_vectors의 복합키 (purchase_id, chunk_index)를 VectorStore가 기대하는 문자열 id로 합친다."""
    return f"{purchase_id}:{chunk_index}"


def _split_chunk_id(cid: str) -> tuple[int, int]:
    purchase_id, chunk_index = cid.split(":")
    return int(purchase_id), int(chunk_index)


class PgVectorStore:
    def __init__(self, conn):
        self._conn = conn  # SQLAlchemy Connection (engine.begin() 등에서 받는다)

    def recreate(self, kind: str, *, dim: int, model: str) -> None:
        table_name, _parent = TABLES[kind]
        # pgvector 확장이 없으면 vector 컬럼 자체를 못 만든다 - 최초 1회만 실제로 동작한다.
        self._conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        table = Base.metadata.tables[table_name]
        table.drop(self._conn, checkfirst=True)
        table.create(self._conn, checkfirst=True)

        meta = Base.metadata.tables["embedding_meta"]
        for key, value in (("model", model), ("dim", str(dim))):
            stmt = pg_insert(meta).values(key=key, value=value)
            stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": stmt.excluded.value})
            self._conn.execute(stmt)

    def hashes(self, kind: str, *, ids=None) -> dict[str, str]:
        table = Base.metadata.tables[TABLES[kind][0]]
        # 테이블이 아직 없으면(최초 실행) UndefinedTable - SAVEPOINT 안에서 시도해야 실패해도
        # 바깥 트랜잭션이 "aborted" 상태로 안 넘어간다. 없으면 아는 지문이 없다는 뜻이라 {}.
        try:
            with self._conn.begin_nested():
                rows = self._conn.execute(
                    select(table.c.purchase_id, table.c.chunk_index, table.c.source_hash)
                ).all()
        except ProgrammingError:
            return {}
        result = {chunk_id(pid, idx): h for pid, idx, h in rows}
        if ids is None:
            return result
        wanted = set(ids)
        return {k: v for k, v in result.items() if k in wanted}

    def upsert(self, kind: str, ids, vectors, *, model: str, hashes) -> None:
        table = Base.metadata.tables[TABLES[kind][0]]
        rows = [
            {"purchase_id": pid, "chunk_index": idx, "vector": vec, "source_hash": h}
            for (pid, idx), vec, h in (
                (_split_chunk_id(item_id), vec, h) for item_id, vec, h in zip(ids, vectors, hashes)
            )
        ]
        stmt = pg_insert(table).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["purchase_id", "chunk_index"],
            set_={"vector": stmt.excluded.vector, "source_hash": stmt.excluded.source_hash},
        )
        self._conn.execute(stmt)

        meta = Base.metadata.tables["embedding_meta"]
        stmt = pg_insert(meta).values(key="model", value=model)
        stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": stmt.excluded.value})
        self._conn.execute(stmt)

    def delete(self, kind: str, ids) -> None:
        if not ids:
            return
        table = Base.metadata.tables[TABLES[kind][0]]
        pairs = [_split_chunk_id(item_id) for item_id in ids]
        self._conn.execute(
            delete(table).where(tuple_(table.c.purchase_id, table.c.chunk_index).in_(pairs))
        )
