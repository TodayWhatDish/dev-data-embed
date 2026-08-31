from app.core.embedder import get_embeddings
from app.domain.embedding_text import product_text
import sqlite3
from app.core.config import DB_PATH

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
rows = con.execute("""
    SELECT
        p.brand, p.name AS product_name,
        pc_parent.name_ko AS category, pc.name_ko AS sub_category,
        GROUP_CONCAT(DISTINCT fp.name_ko) AS target_feeding_purpose,
        p.food_form AS target_food_form,
        GROUP_CONCAT(DISTINCT ing.name_ko) AS ingredients,
        NULL AS tags,
        p.description
    FROM product AS p
    LEFT JOIN product_category AS pc ON pc.product_category_id = p.product_category_id
    LEFT JOIN product_category AS pc_parent ON pc_parent.product_category_id = pc.parent_id
    LEFT JOIN product_feeding_purpose AS pfp ON pfp.product_id = p.product_id
    LEFT JOIN feeding_purpose AS fp ON fp.feeding_purpose_id = pfp.feeding_purpose_id
    LEFT JOIN product_ingredient AS pi ON pi.product_id = p.product_id
    LEFT JOIN ingredient AS ing ON ing.ingredient_id = pi.ingredient_id
    GROUP BY p.product_id
    LIMIT 5
""").fetchall()

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
