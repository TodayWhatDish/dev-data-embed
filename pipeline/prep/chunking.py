# Last Updated : 2026-08-23

""" 리뷰(접두어 포함 문서)를 토큰 한도 안 조각으로 자른다. DB를 모른다.

    들어오는 것 [(purchase_id, "passage:\n..."), ...]
    나가는 것  [{"purchase_id", "chunk_index", "body", "n_tokens"}, ...]

 리뷰는 마크다운 헤더 같은 사람이 만든 절 경계가 없는 자연어라, 
 (MarkdownHeaderTextSplitter)은 안 쓰고 토큰 한도를 넘을 때 문장/구두점 경계에서 자르는 RecursiveCharacterTextSplitter)만 가져온다.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

from app.core.config import EMBED_TOKENIZER
from pipeline.prep.options import CHUNK_OVERLAP, CHUNK_SIZE

_tokenizer = None
_splitter = None


def get_tokenizer():
    """토큰을 세는 자. 무거우니 한 번만 올리고 계속 쓴다."""
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(EMBED_TOKENIZER)
    return _tokenizer


def get_splitter():
    """한도를 넘는 문서만 문장/구두점 경계에서 자르는 분할기."""
    global _splitter
    if _splitter is None:
        _splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            get_tokenizer(), chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
            # separators는 많이 늘릴수록 유지보수 부담이 늘어나기도 하고 효과 체감이 크지않다. (트레이드오프 발생)
            separators=["\n\n", "\n", "다. ", "요. ", ". ", " ", ""], keep_separator="end")
    return _splitter


def count_tokens(text):
    return len(get_tokenizer().encode(text))

#  리뷰 하나가 조각 여러 개로 쪼개질 수 있으니(긴 리뷰의 경우), 
#  쪼갠 뒤에도 "이 조각이 원래 몇 번 리뷰에서 나왔나"를 알아야함.
def split_review(purchase_id, doc):
    """한도 안이면 조각 1개, 넘으면 문장/구두점 경계로 여러 개."""
    n_tokens = count_tokens(doc)
    if n_tokens <= CHUNK_SIZE:
        return [{'purchase_id': purchase_id, 'chunk_index': 0, 'body': doc, 'n_tokens': n_tokens}]

    parts = get_splitter().split_text(doc)
    return [
        {'purchase_id': purchase_id, 'chunk_index': i, 'body': body, 'n_tokens': count_tokens(body)}
        for i, body in enumerate(parts)
    ]


def split_reviews(docs):
    """[(purchase_id, doc), ...] 전체를 조각 목록으로. 부르는 쪽은 이 함수 하나만 알면 된다."""
    chunks = []
    for purchase_id, doc in docs:
        chunks.extend(split_review(purchase_id, doc))
    return chunks
