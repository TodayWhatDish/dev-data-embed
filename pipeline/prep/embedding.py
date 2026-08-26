# Last Updated : 2026-08-26

""" 문서 목록을 벡터로 바꾼다.

    어떻게 벡터로 바꾸는지 알게된다. (어떤 모델을 쓰고, 어떻게 인코딩되는지)
    그 문서가 무엇에 대한 것인지, 어디서 온건지, 결과를 어디에 저장할지는 모른다.
    해당 문서에서는 인자로 받은 텍스트 목록만 보고 벡터 목록을 돌려준다.

    모델 자체는 app/core/embedder.py 가 들고 있다. 질문 벡터(retrieve.py)와
    문서 벡터(build_index.py)가 서로 다른 모델에서 나오면 에러 없이
    검색 결과만 조용히 이상해지기 때문이다.
"""

from app.core.config import BATCH_SIZE
from app.core.embedder import get_embeddings


def embed_texts(
    texts: list[str],
    batch_size: int = BATCH_SIZE,
    show_progress_bar: bool = True,
):
    """문서 목록을 정규화된 벡터로 바꾼다."""
    # normalize_embeddings=True -> 벡터 길이를 1로 맞춰서 이후 코사인 유사도 계산이 내적만으로 가능해짐
    # 색인은 수천 건이라 진행률이 필요하지만, 검색 질의 한 건에는 소음이라 끌 수 있게 열어둔다.
    return get_embeddings().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=show_progress_bar,
    )
