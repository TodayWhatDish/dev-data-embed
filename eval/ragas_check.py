"""ragas로 답변이 [추천 후보] 맥락에서 안 벗어났는지(faithfulness) 채점한다.

    answer_relevancy는 뺐다 - MetricWithEmbeddings라 임베딩 모델이 필요한데 기본값이
    OpenAIEmbeddings라 OPENAI_API_KEY를 요구한다. 우리는 OpenAI를 안 쓰므로(Anthropic/Ollama),
    faithfulness(LLM만 필요)만 쓴다. answer_relevancy가 꼭 필요해지면 e5 임베딩을
    HuggingFaceEmbeddings로 감싸 evaluate(embeddings=...)에 넘길 것.

    ponytail: ragas==0.4.3 이 langchain_community.chat_models.vertexai 를 무조건 import 하는데,
    langchain-community==0.4.2 에서 그 파일 자체가 사라졌다(사용 중단 정리 - 설치 문제가 아니라
    진짜 없음). ragas는 그 클래스를 n-completion 지원 여부 판정용 isinstance 목록에 넣을 뿐이고
    우리는 VertexAI를 아예 안 쓰므로, 빈 클래스로 자리만 채워 import만 통과시킨다.
    langchain-community가 그 파일을 되살리면 이 패치는 조용히 안 타고 넘어간다(무해).
"""
import sys
import types

from eval import SkipCheck


def _patch_ragas_vertexai_import():
    """ragas가 물고 들어오는 langchain_community.chat_models.vertexai 자리를 빈 클래스로 채운다."""
    name = 'langchain_community.chat_models.vertexai'
    if name in sys.modules:
        return
    try:
        __import__(name)
        return  # 이미 존재하면(환경이 고쳐졌으면) 건드리지 않는다
    except ModuleNotFoundError:
        pass
    shim = types.ModuleType(name)
    shim.ChatVertexAI = type('ChatVertexAI', (), {})
    sys.modules[name] = shim


def run():
    _patch_ragas_vertexai_import()
    try:
        from ragas import evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import faithfulness
    except Exception as exc:
        raise SkipCheck(f'{type(exc).__name__}: {exc}') from exc

    from datasets import Dataset

    from app.adapters.stores.llm import chat

    # claude-sonnet-5는 temperature 파라미터 자체를 거부한다(app/adapters/stores/llm.py 참고).
    # ragas는 채점 호출마다 temperature를 직접 밀어넣으므로 bypass_temperature로 그 동작을 끈다.
    judge = LangchainLLMWrapper(chat, bypass_temperature=True)

    sample = {
        'question': ['소형견한테 잘 맞는 다이어트 사료 있나요?'],
        'contexts': [['연어 사료 | 소형견 체중관리용, 후기: 다이어트에 잘 맞고 소형견이 잘 먹음']],
        'answer': ['소형견 체중관리에는 연어 사료가 잘 맞는다는 후기가 있습니다.'],
    }
    result = evaluate(Dataset.from_dict(sample), metrics=[faithfulness], llm=judge)
    faith = result.to_pandas().iloc[0]['faithfulness']
    print(f'  faithfulness={faith:.2f}')
    assert faith >= 0.7, f'faithfulness 낮음: {faith}'
    print('ragas_check OK')


if __name__ == '__main__':
    run()
