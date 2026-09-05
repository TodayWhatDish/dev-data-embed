# Last Updated : 2026-09-04

"""임베딩 모델 싱글톤. 색인(pipeline)과 검색(app)이 같은 인스턴스를 공유해 벡터 공간 일관성 보장.
core/에 두는 이유: features/ 순환 import 방지, 앱 배포 시 pipeline 없이도 떠야 하므로 app/ 측 기반 레이어에 배치.

모델이 로컬(sentence-transformers)이냐 API(OpenAI)냐는 config 의 EMBED_PROFILES 가 정하고,
여기서 그 provider 칸만 보고 갈라진다. 부르는 쪽은 embed_documents/embed_query 두 개만 알면 된다 -
get_embeddings() 가 돌려주는 SentenceTransformer 를 직접 .encode() 하면 API 모델에서 그대로 깨진다.
"""

from sentence_transformers import SentenceTransformer
from app.core.config import (
    EMBED_API_KEY, EMBED_BATCH_SIZE, EMBED_DEVICE, EMBED_MODEL,
    EMBED_NORMALIZE, EMBED_PROVIDER, QUERY_PREFIX,
)


_embeddings = None
_client = None

def get_embeddings() -> SentenceTransformer:
    """로컬 임베딩 모델 인스턴스 반환. 최초 호출 시 로드.

    provider='openai' 프로파일에는 올릴 가중치가 없다 - 그 경우 부르면 안 되고,
    조용히 다른 벡터를 돌려주느니 여기서 막는다.
    """
    global _embeddings
    if EMBED_PROVIDER != "st":
        raise RuntimeError(
            f"{EMBED_MODEL} 은 provider='{EMBED_PROVIDER}' 라 로컬로 올릴 수 없습니다. "
            "embed_documents()/embed_query() 를 쓰세요."
        )
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


def _get_client():
    """OpenAI 클라이언트. 키가 없으면 첫 호출에서 바로 세운다 - 요청을 다 보낸 뒤 401 로 알면 늦다."""
    global _client
    if _client is None:
        if not EMBED_API_KEY:
            raise SystemExit(
                f"{EMBED_MODEL} 을 쓰려면 .env 에 EMBED_API_KEY (또는 OPENAI_API_KEY) 가 있어야 합니다."
            )
        from openai import OpenAI
        _client = OpenAI(api_key=EMBED_API_KEY)
    return _client


def _embed_openai(texts: list[str]) -> list[list[float]]:
    """API 로 임베딩한다. 한 요청에 batch_size 개씩 나눠 보낸다.

    text-embedding-3-* 는 이미 길이 1 로 돌아오지만, EMBED_NORMALIZE 를 끄고 켜는 실험이
    로컬 모델과 API 모델에서 다르게 굴러가면 비교가 안 되므로 여기서도 같은 스위치를 건다.
    """
    if not texts:
        return []

    import numpy as np

    client = _get_client()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        response = client.embeddings.create(model=EMBED_MODEL, input=batch)
        # 응답은 index 로 원래 자리를 알려준다. 순서를 가정하지 않고 그 값으로 되돌린다 -
        # 어긋나면 벡터와 조각이 통째로 뒤바뀌는데 에러 없이 검색 품질만 무너진다.
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))

    if not EMBED_NORMALIZE:
        return vectors

    array = np.asarray(vectors, dtype="float32")
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (array / norms).tolist()


def embed_documents(texts:list[str]) -> list[list[float]]:
    """현재 리스트를 벡터 리스트로 변환. 배치 처리 + 정규화."""
    if EMBED_PROVIDER == "openai":
        return _embed_openai(texts)

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
    bge/OpenAI 는 접두사가 빈 문자열이라 그대로 지나간다.
    """
    return embed_documents([QUERY_PREFIX + text])[0]
