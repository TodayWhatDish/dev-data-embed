# Last Updated : 2026-08-30

"""검색 결과를 LLM 이 읽을 질의문으로 조립한다. 여기서는 DB 도 모델도 건드리지 않는다.

    입력(질문·프로필·후보)만 받아 문자열을 돌려주는 순수 함수라, LLM 을 부르지 않고도
    "무엇을 물어봤는지"를 눈으로 검사할 수 있다. 프롬프트가 틀린 것인지 모델이 틀린
    것인지는 이 경계가 없으면 구분이 안 된다.

    조립 규칙 하나 ─ 후보는 반드시 ID 를 달고 나간다.
    LLM 이 상품명을 한 글자 바꿔 답해도 이름 대조로는 못 잡는다. 답을 ID 로 받아야
    recommending.py 가 "후보에 있는 ID 인가"를 기계적으로 검증할 수 있다.
"""
from typing import Any

# 모델에게 형식을 말로 설명하는 대신 예시를 보여준다. 작은 모델은 설명보다 예시를 잘 따른다.
ANSWER_SHAPE = """{
  "answer": "사용자에게 보여줄 한국어 답변",
  "picks": [
    {"product_id": "F0042", "reason": "이 상품을 고른 이유", "evidence": ["O00418"]}
  ]
}"""

SYSTEM = """너는 반려동물 사료·간식 추천 도우미다. 한국어로만 답한다.

지켜야 할 규칙:
1. 아래 '후보' 목록에 있는 상품만 추천한다. 목록에 없는 상품을 만들어내지 마라.
2. product_id 는 후보에 적힌 것을 그대로 옮겨 적는다.
3. 추천 이유는 후보에 붙은 후기 내용에서만 가져온다. 후기에 없는 효능을 지어내지 마라.
4. evidence 에는 근거로 삼은 후기 ID 를 적는다.
5. 질문에 맞는 후보가 없으면 picks 를 빈 배열로 두고 answer 에 그렇게 말한다.
6. 설명이나 인사 없이 아래 JSON 형식 하나만 출력한다. 코드블록도 쓰지 마라.

출력 형식:
""" + ANSWER_SHAPE


def format_profile(profile: dict[str, Any]) -> str:
    """프로필 dict 를 한 줄로. 빈 값은 아예 적지 않는다.

    '알레르기: 없음' 처럼 빈 값을 굳이 채우면, 모델이 그걸 조건으로 읽고
    "알레르기가 없는 아이라서 골랐다" 같은 근거 없는 문장을 만든다.
    """
    labels = {"animal_category": "축종", "size_category": "체구", "allergy": "알레르기"}
    filled = [f"{labels[k]} {profile[k]}" for k in labels if profile.get(k)]
    return " / ".join(filled) if filled else "정보 없음"


def format_candidates(candidates: list[dict[str, Any]], max_reviews: int = 2) -> str:
    """후보 목록을 모델이 읽을 블록으로. 상품 한 건이 머리줄 + 근거 후기 몇 줄이다.

    후기는 상품당 max_reviews 건까지만 싣는다. 전부 실으면 후보 수만큼 곱해져
    프롬프트가 길어지는데, 같은 상품의 후기는 서로 내용이 겹쳐서 늘린 만큼의
    판단 근거가 늘지 않는다.
    """
    if not candidates:
        return "(없음)"

    blocks = []
    for c in candidates:
        head = f"[{c['product_id']}] {c['brand']} {c['name']}"
        spec = f"{c['category']}, {c['food_form']}"
        if c.get("purposes"):
            spec += f", {c['purposes']} 목적"
        if c.get("price_krw"):
            spec += f", {c['price_krw']:,}원"
        lines = [f"{head} ({spec})"]
        if c.get("description"):
            lines.append(f"  설명: {c['description']}")
        for r in c["reviews"][:max_reviews]:
            lines.append(f"  후기 {r['id']} (별점 {r['rating']}점): {r['body']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_messages(question: str, profile: dict[str, Any],
                   candidates: list[dict[str, Any]], n_pick: int = 3,
                   repair: str = "") -> list[tuple[str, str]]:
    """chat.invoke() 에 그대로 넘길 (역할, 내용) 목록.

    repair 는 재시도용이다. 앞선 응답이 왜 퇴짜맞았는지를 붙여서 다시 묻는다.
    같은 프롬프트로 그냥 재시도하면 모델은 대개 같은 실수를 반복한다.
    """
    user = (
        f"질문: {question}\n"
        f"반려동물: {format_profile(profile)}\n\n"
        f"후보 (이 안에서만 고를 것):\n{format_candidates(candidates)}\n\n"
        f"위 후보 중 최대 {n_pick}개를 골라 JSON 으로만 답해라."
    )
    if repair:
        user += f"\n\n직전 응답이 규칙을 어겼다: {repair}\n형식과 규칙을 지켜 다시 답해라."
    return [("system", SYSTEM), ("human", user)]
