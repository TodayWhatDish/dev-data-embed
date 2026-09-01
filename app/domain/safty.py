"""
아직 검수 안된 코드
상품 주의사항에서 판매하면 안 되는 조건을 찾는다.
"""

import re

BAN = re.compile(r"(사용을 권하지 않|사용하지 마|사용을 피하|사용을 삼가|사용 금지)")

SENSITIVE = "민감성"


# 주의사항 섹션들에서 {상품id: [금지 문장]} 을 만든다
def extract_bans(sections):
    bans = {}
    for product_id, text in sections:
        for sentence in re.split(r"(?<=[.!?])\s+|\n", text or ""):
            if BAN.search(sentence) and SENSITIVE in sentence:
                bans.setdefault(product_id, []).append(sentence.strip())
    return bans


# 이 피부 타입 고객에게 추천하면 안 되는 상품 아이디들
def blocked_for(skin_type, bans):
    if skin_type == SENSITIVE:
        return set(bans)
    return set()


# 왜 막혔는지 근거 문장. 근거 없는 차단은 사람이 못 고친다
def reason_for(product_id, bans):
    sentences = bans.get(product_id, [])
    return sentences[0] if sentences else ""
