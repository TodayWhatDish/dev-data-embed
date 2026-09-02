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

from app.core.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER

# 단순 float로 둔다 - httpx.Timeout은 ChatOpenAI 전용 인자라 다른 프로바이더 클라이언트에서 검증 오류가 난다.
TIMEOUT = 300.0

# base_url은 OpenAI 호환 엔드포인트(Ollama 등)에만 의미가 있다 - None이면 안 넘긴다.
_common = {"model": LLM_MODEL, "model_provider": LLM_PROVIDER, "api_key": LLM_API_KEY, "timeout": TIMEOUT}
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
