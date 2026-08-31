# Last updated: 2026-08-27
# Last Updated : 2026-08-23

""" 리뷰(접두어 포함 문서)를 토큰 한도 안 조각으로 자른다. 

    어떻게 자르는지는 앎 (토큰 한도, 문장과 구두점의 경계)
    DB는 모른다 : 이게 어디서 왔는지, 어디에 저장할지는 모름.
    인자로 받은 (purchase_id,doc) 목록만 보고 조각 목록을 돌려줄 뿐이다.

    Input :  [(purchase_id, "passage:\n..."), ...]       
    Output :  [{"purchase_id", "chunk_index", "body", "n_tokens"}, ...]

    리뷰는 마크다운 헤더 같은 사람이 만든 절 경계가 딱히 없는 자연어라, 
    MarkdounHeaderTextSplitter는 쓰지 않고, 문장,구두점 경계에서 자르는 
    RecursiveCharacterTextSplitter만 사용한다.

"""
import sqlite3
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

from app.core.config import EMBED_TOKENIZER
from pipeline.prep.options import CHUNK_OVERLAP, CHUNK_SIZE, SEPARATORS

_tokenizer = None
_splitter = None


def get_tokenizer():
    """토큰 카운터. 무거우니 한 번만 올리고 계속 쓴다."""
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
            separators=SEPARATORS, keep_separator="end")
    return _splitter


def count_tokens(text):
    return len(get_tokenizer().encode(text))

def build_review_doc(row: sqlite3.Row) -> str:
    """리뷰 한 건을 임베딩용 문장으로 조립한다.

    size_category/breed/allergy는 안 넣는다 - retrieve.py의 FILTERS가 이미
    SQL WHERE로 걸러주는 값이라, 여기 또 넣으면 모든 문서가 거의 같은
    보일러플레이트가 돼서 코사인 유사도가 내용과 무관하게 뭉친다.
    ingredients는 반대다 - 필터가 안 걸러주는 값이면서, 같은 카테고리·같은 급여목적
    안에서 상품을 실제로 가르는 유일한 객관적 신호라서 넣는다.
    """
    purpose = f"{row['target_feeding_purpose']} 목적" if row['target_feeding_purpose'] else "목적 미기재"
    category = f"{row['category']}/{row['sub_category']}" if row['category'] else row['sub_category']
    ingredients = f"주원료: {row['ingredients']} " if row['ingredients'] else ""
    return (
        "passage: " # 공식 e5 포맷
        f"{category} {row['product_name']} "
        f"({purpose}, {row['target_food_form']}) "
        f"{ingredients} "
        f"별점 {row['rating']}점 후기: {row['review']}"
    )

#  리뷰 하나가 조각 여러 개로 쪼개질 수 있으니(긴 리뷰의 경우), 
#  쪼갠 뒤에도 "이 조각이 원래 몇 번 리뷰에서 나왔나"를 알아야함.
def split_review(purchase_id: int, doc: str, product_name: str):
    """한도 안이면 조각 1개, 넘으면 문장/구두점 경계로 여러 개.

    쪼갠 뒤 조각마다 상품명을 다시 접두어로 붙인다 - 안 그러면 뒤쪽 조각은
    어느 상품 얘기인지 알려주는 토큰이 하나도 안 남는다.
    """
    n_tokens = count_tokens(doc)
    if n_tokens <= CHUNK_SIZE:
        return [{'purchase_id': purchase_id, 'chunk_index': 0, 'body': doc, 'n_tokens': n_tokens}]

    parts = get_splitter().split_text(doc)
    tagged = [f"[{product_name}] {body}"for body in parts]
    return [
        {'purchase_id': purchase_id, 'chunk_index': i, 'body': body, 'n_tokens': count_tokens(body)}
        for i, body in enumerate(tagged)
    ]


def split_reviews(docs: list[tuple]):
    """[(purchase_id, doc), ...] 전체를 조각 목록으로. 부르는 쪽은 이 함수 하나만 알면 된다."""
    chunks = []
    for purchase_id, doc, product_name in docs:
        chunks.extend(split_review(purchase_id, doc, product_name))
    return chunks

