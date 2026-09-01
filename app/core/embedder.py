# Last Updated : 2026-08-26

"""임베딩 모델 싱글톤. 색인(pipeline)과 검색(app)이 같은 인스턴스를 공유해 벡터 공간 일관성 보장.
core/에 두는 이유: features/ 순환 import 방지, 앱 배포 시 pipeline 없이도 떠야 하므로 app/ 측 기반 레이어에 배치.
"""

from sentence_transformers import SentenceTransformer
from app.core.config import EMBED_MODEL, EMBED_DEVICE, EMBED_BATCH_SIZE, EMBED_NORMALIZE, QUERY_PREFIX


_embeddings = None

def get_embeddings() -> SentenceTransformer:
    """임베딩 모델 인스턴스 반환. 최초 호출 시 로드."""
    global _embeddings
    if _embeddings is not None:
        return _embeddings
    
    from huggingface_hub.utils import disable_progress_bars, logging as hub_logging
    hub_logging.set_verbosity_error()
    disable_progress_bars()

    from sentence_transformers import SentenceTransformer

    _embeddings = SentenceTransformer(
        EMBED_MODEL,
        device=EMBED_DEVICE
    )

    return _embeddings

def embed_documents(texts:list[str]) -> list[list[float]]:
    """현재 리스트를 벡터 리스트로 변환. 배치 처리 + 정규화."""
    model = get_embeddings()
    return model.encode(
        texts,
        batch_size=EMBED_BATCH_SIZE,
        normalize_embeddings=EMBED_NORMALIZE,
        show_progress_bar=False,
    ).tolist()


def embed_query(text: str) -> list[float]:
    """단일 쿼리를 벡터로 변환. 모델이 요구하는 질의 접두사를 붙인다.

    e5 계열은 'query: ' 가 없으면 문서 벡터와 다른 자리에 찍혀 유사도가 무너진다.
    지금은 vector_db.search() 가 직접 붙여 쓰고 있어 호출되는 데가 없지만,
    접두사 없이 부르면 '조용히' 틀린 벡터를 돌려주는 함수를 남겨두지 않는다.
    """
    return embed_documents([QUERY_PREFIX + text])[0]

