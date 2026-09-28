# 리뷰 조각 + 임베딩 벡터 ORM 모델. 청킹은 pipeline/chunk.py, 임베딩은 pipeline/embed.py,
# 상품/고객 벡터는 pipeline/prep_rec.py가 채운다.
# 예전엔 sqlite-vec(로컬 SQLite 확장)을 썼는데, DB가 Supabase(Postgres)로 이관되면서
# pgvector 확장으로 옮겼다 - vector 타입 하나만 다르고 나머지 컬럼은 그대로다.

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKeyConstraint, Integer, Text

from app.core.config import EMBED_DIM
from app.core.db import Base


class Chunk(Base):
    __tablename__ = "chunks"

    purchase_id = Column(Integer, primary_key=True)
    chunk_index = Column(Integer, primary_key=True)
    body = Column(Text)
    n_tokens = Column(Integer)


class ChunkVector(Base):
    __tablename__ = "chunk_vectors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_id", "chunk_index"], ["chunks.purchase_id", "chunks.chunk_index"]
        ),
    )

    purchase_id = Column(Integer, primary_key=True)
    chunk_index = Column(Integer, primary_key=True)
    # EMBED_DIM은 EMBED_MODEL 하나로 고정돼 있다(config.py) - 모델을 바꾸면 재색인과
    # 함께 이 컬럼도 다시 만들어야 한다(PgVectorStore.recreate가 담당).
    vector = Column(Vector(EMBED_DIM), nullable=False)
    source_hash = Column(Text, nullable=False)


class ProductVector(Base):
    """상품 요약 벡터. 5단계 검증(pipeline/verify.py)의 기준선이다. pipeline/prep_rec.py가 채운다."""

    __tablename__ = "product_vectors"

    product_id = Column(Integer, primary_key=True)
    vector = Column(Vector(EMBED_DIM), nullable=False)
    # 상품 문장 + 모델의 지문(embedding_sync.fingerprint). 같으면 다시 임베딩하지 않는다.
    source_hash = Column(Text, nullable=False)


class CustomerVector(Base):
    """고객 벡터 = 홀드아웃을 뺀 그 고객 조각 벡터의 평균. pipeline/prep_rec.py가 채운다."""

    __tablename__ = "customer_vectors"

    customer_id = Column(Integer, primary_key=True)
    vector = Column(Vector(EMBED_DIM), nullable=False)


class EmbeddingMeta(Base):
    """색인 당시 모델/차원/조각 지문. retrieve.py의 check_freshness()가 지금 설정과 대조한다."""

    __tablename__ = "embedding_meta"

    key = Column(Text, primary_key=True)
    value = Column(Text)
