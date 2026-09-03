# Last Updated : 2026-09-03

"""내용이 바뀐 조각만 찾아 벡터를 최신 상태로 맞춘다.

무엇을 다시 만들지 고르는 일만 한다 — 자르는 건 pipeline/prep/chunking.py 가,
넣고 빼는 건 adapters/stores/sqlite_store.py 가 안다.
"""

from app.adapters.stores import get_store
from app.core.config import EMBED_DIM, EMBED_MODEL
from app.core.embedder import embed_documents
from app.domain.embedding_text import source_hash


def fingerprint(text: str, model: str = EMBED_MODEL) -> str:
    """이 글을 이 모델로 임베딩했다는 영수증. 모델이 바뀌면 같은 글이어도 지문이 달라진다."""
    return source_hash(f"{model}\n{text}")


def sync(con, kind: str, ids: list[str], texts: list[str], *,
         full: bool = False, model: str = EMBED_MODEL) -> dict:
    """ids/texts 를 저장소와 맞춘다. 바뀐 것만 임베딩하고 없어진 것은 지운다.

    ids[i] 와 texts[i] 가 같은 조각을 가리킨다는 것이 이 함수의 유일한 전제다.
    """
    store = get_store(con)
    marks = [fingerprint(text, model) for text in texts]

    # 전량이면 저장된 지문을 안 본다 - 어차피 표를 새로 만든다.
    known = {} if full else store.hashes(kind)
    if full or not known:
        store.recreate(kind, dim=EMBED_DIM, model=model)
        known = {}

    # 처음 보는 id 는 known.get() 이 None 이라 자동으로 '다름'이 된다.
    todo = [i for i, (item_id, mark) in enumerate(zip(ids, marks))
            if known.get(item_id) != mark]

    # 돈과 시간이 드는 자리는 여기 하나뿐이다. 고른 것만 모델에 넘긴다.
    if todo:
        vectors = embed_documents([texts[i] for i in todo])
        store.upsert(kind, [ids[i] for i in todo], vectors,
                     model=model, hashes=[marks[i] for i in todo])

    # 저장소엔 있는데 지금 목록엔 없는 것 = 원본에서 사라진 조각.
    alive = set(ids)
    gone = [item_id for item_id in known if item_id not in alive]
    store.delete(kind, gone)

    return {"embedded": len(todo), "skipped": len(ids) - len(todo), "deleted": len(gone)}
