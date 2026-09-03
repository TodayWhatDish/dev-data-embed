# Last updated: 2026-09-03
# Last Updated : 2026-09-02

""" 모델에 말을 거는 자리로 클라이언트 두 개를 만들어 두는 것이 전부다.

    init_chat_model()이 LLM_PROVIDER 값만 보고 알맞은 LangChain 클라이언트(ChatOpenAI/
    ChatAnthropic/...)를 골라준다. 로컬(Ollama)과 상용의 분기는 core/config.py 한 곳에만
    있고, 여기와 부르는 쪽(features/*)은 프로바이더가 뭐든 안 바뀐다 - .env에서
    LLM_PROVIDER/LLM_API_KEY/API_MODEL만 바꾸면 상용 API가 통째로 바뀐다.

    프롬프트 자체를 조립하는 일은 domain/prompting 이 진행하며, 무엇을 어떤 순서로
    시키는지는 app/features 쪽이 담당한다.
"""
from langchain.chat_models import init_chat_model
from app.core.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER, VERIFY_MODEL
from app.core.trace import tracer

# httpx.Timeout(connect=..., read=..., write=..., pool=...)로 세분화하고 싶었지만
# ChatAnthropic의 timeout 필드가 pydantic으로 float만 받는다 - httpx.Timeout을 넣으면
# ValidationError. ChatOpenAI 쪽은 Any라 받아주지만 _common을 두 프로바이더가 같이 쓰니
# 공통분모인 float로 통일한다. connect/read를 진짜 나눠야 하면 프로바이더별 분기가 필요하다.
TIMEOUT = 60.0
# base_url은 OpenAI 호환 엔드포인트(Ollama 등)에만 의미가 있다 - None이면 안 넘긴다.
# callbacks에 tracer를 꽂아 두면 chat/chat_answer 호출마다 logs/query_log.jsonl에 자동으로 남는다.
_common = {"model": LLM_MODEL, "model_provider": LLM_PROVIDER, "api_key": LLM_API_KEY,
           "timeout": TIMEOUT, "callbacks": [tracer]}
if LLM_BASE_URL:
    _common["base_url"] = LLM_BASE_URL

# temperature: 일부 최신 모델(예: claude-sonnet-5)은 이 값을 아예 안 받고 400을 뱉는다 - 그런 모델은 생략한다.
_temps = {} if LLM_PROVIDER == "anthropic" else {"temperature": 0}
chat = init_chat_model(**_temps, **_common)

# 정형 출력(추천)용은 위 chat 그대로 두고, 자유 텍스트 답변용을 하나 더 둔다.
_answer_temps = {} if LLM_PROVIDER == "anthropic" else {"temperature": 0.3}  # 답변은 표현이 조금 다양해도 되니 0보다 크게
chat_answer = init_chat_model(**_answer_temps,
                              stream_usage=True,       # 스트리밍 중 토큰 집계
                              **_common)

# 반증(answering.verify)용 - chat_answer가 만든 답을 같은 모델(chat)로 채점하면 자기 답을
# 관대하게 채점하는 self-evaluation bias가 생긴다. model만 다르게, 나머지 설정은 그대로 재사용한다.
chat_verify = init_chat_model(**_temps, **{**_common, "model": VERIFY_MODEL})
