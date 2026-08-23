# Last Updated : 2026-08-23

""" 문서 목록을 벡터로 바꾼다.

    어떻게 벡터로 바꾸는지 알게된다. (어떤 모델을 쓰고, 어떻게 인코딩되는지)
    그 문서가 무엇에 대한 것인지, 어디서 온건지, 결과를 어디에 저잘할지는 모른다.
    해당 문서에서는 인자로 받은 텍스트 목록만 보고 벡터 목록을 돌려준다.

"""

from sentence_transformers import SentenceTransformer

from app.core.config import EMBED_MODEL

_model = None

def get_model():
    """모델을 한 번만 올리고 계속 쓴다."""
    pass

def embed_texts(texts: str):
    """벡터 길이를 정규화(1로 맞춰서) 이후 코사인 유사도가 내적만으로 계산되게 할 것"""
    pass