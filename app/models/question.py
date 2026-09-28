# 고객 질문 기록 ORM 모델. /ask, /ask/me 한 건 = 한 행. 관리자 대시보드 '질문' 탭이 읽는다.
# 예전엔 logs/query_log.jsonl 에 남겼는데 컨테이너 파일이라 재배포마다 사라져 DB 로 옮겼다.

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.user import NOW


class CustomerQuestion(Base):
    __tablename__ = "customer_question"

    question_id = Column(Integer, primary_key=True)
    # 회원이 탈퇴(삭제)돼도 질문 기록은 남긴다 - 누가 물었는지만 비운다
    user_id = Column(Integer, ForeignKey("user.user_id", ondelete="SET NULL"))
    pet_id = Column(Integer, ForeignKey("pet.pet_id", ondelete="SET NULL"))
    user_query = Column(Text, nullable=False)
    # 후보 [{product_id, name, product_type, score}] - 표시용 스냅샷이라 정규화하지 않는다
    matched = Column(JSONB, nullable=False, server_default="[]")
    answer = Column(Text, nullable=False, server_default="")
    ok = Column(Boolean, nullable=False)
    error = Column(Text)
    created_at = Column(Text, nullable=False, server_default=NOW)
