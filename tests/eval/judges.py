"""채점기의 '자' 부분만 따로 검산한다.  py -m tests.eval.judges

format_check 와 ragas_check 는 LLM 이 떠 있어야 끝까지 돈다. 그런데 정작 틀리기 쉬운
곳은 LLM 이 아니라 응답을 해석하는 쪽이다 - extract_json 이 울타리를 못 걷으면 멀쩡한
답을 '파싱 실패'로 세고, 그러면 고칠 곳을 프롬프트에서 찾게 된다. 틀린 자로 잰 숫자는
없느니만 못하다.

여기는 LLM 도 DB 도 안 부른다. 입력을 손으로 만들어 넣고 나온 값만 본다.
"""
from eval.format_check import extract_json, judge
from eval.ragas_check import check_grounding

VALID = {11, 12, 13, 14, 15}


def picks(*ids):
    """product_id 목록을 모델이 낸 모양의 JSON 문자열로 만든다."""
    import json

    body = {"picks": [{"product_id": i, "reason": "이유"} for i in ids]}
    return json.dumps(body, ensure_ascii=False)


if __name__ == '__main__':
    # 1. extract_json - 모델이 JSON 앞뒤에 뭘 붙이든 알맹이만 남아야 한다
    assert extract_json('{"a": 1}') == '{"a": 1}'
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('```\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('네, 추천해 드릴게요!\n{"a": 1}\n감사합니다') == '{"a": 1}'
    # 중괄호가 아예 없으면 걷을 게 없다 - 원문을 그대로 넘겨 judge 가 파싱 실패로 센다
    assert extract_json('죄송하지만 못 하겠습니다') == '죄송하지만 못 하겠습니다'
    assert extract_json('') == ''
    assert extract_json(None) == ''
    print('extract_json  울타리·인사말·빈 값 6가지 통과')

    # 2. judge - 다섯 칸이 각각 제 것만 잡는지. 한 칸이 다른 칸을 덮으면 표가 거짓말을 한다
    ok = judge(picks(11, 12, 13, 14, 15), VALID)
    assert ok == {'json_ok': True, 'n_picks': 5, 'out_of_range': 0,
                  'duplicated': False, 'schema_ok': True}, ok

    outside = judge(picks(11, 12, 99), VALID)
    assert outside['out_of_range'] == 1, outside
    # 후보 밖 ID 를 냈어도 '모양'은 지킨 것이다 - 스키마 통과와 섞어 세면 안 된다
    assert outside['schema_ok'] is True, outside
    assert outside['n_picks'] == 3, outside

    dup = judge(picks(11, 11, 12), VALID)
    assert dup['duplicated'] is True, dup
    assert dup['out_of_range'] == 0, dup

    broken = judge('그냥 줄글로 답합니다', VALID)
    assert broken['json_ok'] is False and broken['schema_ok'] is False, broken
    assert broken['n_picks'] == 0, broken

    # 호출이 터졌을 때 format_check 이 넘기는 값. 파싱 실패로 세야 한다
    assert judge('', VALID)['json_ok'] is False

    # JSON 이긴 한데 우리 스키마가 아닌 것. 파싱은 됐으니 json_ok 는 True 다
    wrong_shape = judge('{"picks": [{"번호": 11}]}', VALID)
    assert wrong_shape['json_ok'] is True, wrong_shape
    assert wrong_shape['schema_ok'] is False, wrong_shape
    assert wrong_shape['out_of_range'] == 1, wrong_shape  # product_id 가 없으니 후보 밖이다

    # 최상위가 목록이면 우리 모양이 아니다
    assert judge('[1, 2, 3]', VALID)['json_ok'] is False
    print('judge          정상·후보밖·중복·깨짐·빈값·다른모양 8가지 통과')

    # 3. check_grounding - 후보에 없는 상품명을 답변이 말했나 (LLM 없이 잡는 지어냄)
    all_names = {1: '멍푸드 사료 01호', 2: '도그밀 사료 01호', 3: '퍼피랩 사료 01호'}
    cands = [{'name': '멍푸드 사료 01호'}, {'name': '도그밀 사료 01호'}]

    clean = check_grounding('멍푸드 사료 01호를 권합니다.', cands, all_names)
    assert clean == {'n_mentioned': 1, 'n_from_candidates': 1,
                     'n_invented': 0, 'invented': []}, clean

    made_up = check_grounding('퍼피랩 사료 01호가 좋습니다.', cands, all_names)
    assert made_up['n_invented'] == 1, made_up
    assert made_up['invented'] == ['퍼피랩 사료 01호'], made_up

    # 상품을 하나도 안 말한 답변(자료에 없다 같은)은 지어낸 것도 없다
    none = check_grounding('자료에 없습니다.', cands, all_names)
    assert none['n_mentioned'] == 0 and none['n_invented'] == 0, none
    print('check_grounding 후보안·후보밖·언급없음 3가지 통과')

    print('\n채점기의 자는 성하다')
