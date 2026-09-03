"""answering.verify()의 2차 LLM 채점(chat_verify)이 맞는 답을 맞다고, 틀린 답을 틀리다고
    보는지 골든 셋으로 확인한다. 프롬프트나 모델을 바꿨을 때 채점 감이 흐트러지면 여기서 잡힌다.

    golden_qa.json: [{id, detail, answer, expect_high}, ...]
    detail/answer 모양은 app/features/answering.verify() 그대로 - DB 없이 값만 넣는다.
"""
import json
from pathlib import Path

from app.features.answering import verify

GOLDEN_PATH = Path(__file__).parent / 'golden_qa.json'


def run():
    cases = json.loads(GOLDEN_PATH.read_text(encoding='utf-8'))
    for case in cases:
        result = verify(case['detail'], case['answer'])
        accuracy = result['accuracy']
        ok = accuracy >= 0.7 if case['expect_high'] else accuracy <= 0.3
        print(f"  [{case['id']}] accuracy={accuracy:.2f} (기대: {'높음' if case['expect_high'] else '낮음'}) "
              f"-> {'OK' if ok else 'FAIL'} | {result['note']}")
        assert ok, f"{case['id']}: accuracy={accuracy}, note={result['note']}"
    print('golden OK')


if __name__ == '__main__':
    run()
