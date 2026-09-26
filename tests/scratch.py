from app.core.db import get_engine
from app.core.embedder import get_embeddings
from app.domain.embedding_text import product_text
from pipeline.prep_rec import product_rows_stmt

# 상품 문장은 prep_rec 이 실제로 임베딩하는 쿼리 그대로 만든다.
with get_engine().connect() as con:
    rows = con.execute(product_rows_stmt().limit(5)).mappings().all()

docs = [product_text(r) for r in rows]
for d in docs:
    print(d)

model = get_embeddings()
vecs = model.encode(docs, normalize_embeddings=True)

print("\n상품 5개 pairwise 코사인 유사도:")
for i in range(len(docs)):
    for j in range(i + 1, len(docs)):
        sim = float(vecs[i] @ vecs[j])
        print(f"  [{i}] vs [{j}]: {sim:.3f}")
