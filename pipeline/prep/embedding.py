# Last Updated : 2026-08-24

""" 문서 목록을 벡터로 바꾼다.

    어떻게 벡터로 바꾸는지 알게된다. (어떤 모델을 쓰고, 어떻게 인코딩되는지)
    그 문서가 무엇에 대한 것인지, 어디서 온건지, 결과를 어디에 저장할지는 모른다.
    해당 문서에서는 인자로 받은 텍스트 목록만 보고 벡터 목록을 돌려준다.

"""

from sentence_transformers import SentenceTransformer

from app.core.config import EMBED_MODEL,BATCH_SIZE

from langchain_huggingface import HuggingFaceEmbeddings
_model = None

def get_model():
    """모델을 한 번만 올리고 계속 쓴다."""
    
    # chunking.py 의 토크나이저와 같은 이유로 전역에 한 번만 담아둔다.
    global _model
    if _model is None:
        model = HuggingFaceEmbeddings(
        model_name="intfloat/multilingual-e5-small",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True, "batch_size": BATCH_SIZE}
        )
    return _model

def embed_texts(texts: list[str], batch_size: int = BATCH_SIZE, show_progress_bar: bool = True):
    """벡터 길이를 정규화(1로 맞춰서) 이후 코사인 유사도가 내적만으로 계산되게 할 것"""
    # normalize_embeddings=True -> 벡터 길이를 1로 맞춰서 이후 코사인 유사도 계산이 내적만으로 가능해짐
    # 색인은 수천 건이라 진행률이 필요하지만, 검색 질의 한 건에는 소음이라 끌 수 있게 열어둔다.
    return get_model().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=show_progress_bar,
    )
