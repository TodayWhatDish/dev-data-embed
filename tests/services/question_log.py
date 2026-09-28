"""관리자 /ask 질문은 '질문' 탭 기록에 안 남고, 고객 /ask/me 질문만 남는지 본다.

    py -m tests.services.question_log
"""

from app.graph import nodes

logged = []
nodes.log_customer_question = lambda **kw: logged.append(kw)

kw = dict(matches=[], answer="", ok=False, error="후보 없음")
nodes._log({"question": "관리자 질문", "log_question": False}, **kw)
assert logged == [], "관리자 질문이 기록됐다"

nodes._log({"question": "고객 질문", "log_question": True}, **kw)
nodes._log({"question": "기본값"}, **kw)  # 플래그가 없으면 기록한다 (/ask/me)
assert [r["user_query"] for r in logged] == ["고객 질문", "기본값"]
print("ok")
