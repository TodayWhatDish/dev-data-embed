# Last Updated : 2026-08-25

"""임베딩 모델(SentenceTransformer)을 만드는 자리를 여기 하나로 모은다.

여러 파일이 각자 모델을 만들면 질문 벡터와 문서 벡터가 서로 다른 기준으로
만들어질 수 있는데, 그래도 에러 없이 검색 결과만 이상해진다. 그래서 다른
파일은 전부 이렇게 쓴다 ─
    from app.core.embedder import get_embeddings
"""


from sentence_transformers import SentenceTransformer
from app.core.config import EMBED_MODEL

_model = None

def get_embeddings():
    """모델을 한 번만 올리고 계속 쓴다."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model