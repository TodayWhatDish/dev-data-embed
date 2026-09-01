"""
[아직 검수 안된 코드]
문장에서 전화번호와 이메일 같은 개인정보를 가린다.
"""

import re

PHONE = re.compile(r"01[016-9][-.\s]?\d{3,4}[-.\s]?\d{4}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")

KAKAO = re.compile(r"[^.!?]*카톡[^.!?]*[.!?]?")
CONTACT = re.compile(r"[^.!?]*(문자|연락|공구|디엠|DM)[^.!?]*[.!?]?")


# 도시 목록으로 주소 정규식을 만든다. 목록이 비면 None
def build_address_pattern(cities):
    if not cities:
        return None
    ordered = sorted(set(cities), key=len, reverse=True)
    return re.compile(r"(?:%s)(?:\s?[가-힣]+(?:동|구|읍|면|로|길))?" % "|".join(ordered))


# 가리고 나면 생기는 연속 공백을 정리한다
def _tidy(text):
    return re.sub(r"\s{2,}", " ", text).strip()


# 개인정보를 지운다. 되돌릴 수 없으므로 나가는 글에만 쓴다
def mask(text, *, names=(), address=None):
    if not text:
        return text
    text = KAKAO.sub(" ", text)
    text = CONTACT.sub(" ", text)
    text = PHONE.sub("[연락처]", text)
    text = EMAIL.sub("[메일]", text)
    if address is not None:
        text = address.sub("[주소]", text)
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        if name in text:
            text = text.replace(name, "[이름]")
    return _tidy(text)
