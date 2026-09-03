"""자체검증 스크립트를 pytest 로 한 번에 돌린다.

원본은 `py -m tests.domain_and_repo.pet` 로 그대로 도는 print+assert 스크립트다 (CLAUDE.md).
그 형태를 pytest 함수로 다시 쓰지 않는 이유는, 스크립트가 곧 읽는 문서 노릇을 하고 있어서다.
여기서는 **모아 돌리는 일만** 한다 - 하나가 깨지면 어느 모듈인지 이름으로 나온다.

    pytest                # 빠른 것만 (아래 SELFCHECKS)
    pytest -m slow        # 임베딩 모델 올리고 DB 에 쓰는 것까지
    pytest -k pet         # 이름으로 골라서

새 자체검증을 만들면 여기 목록에 한 줄 더한다. 파일을 만들기만 하고 안 넣으면 안 돌아간다.
"""
import runpy

import pytest

# DB 만 읽고 몇십 ms 안에 끝나는 것들. 커밋 전에 이건 다 돌린다
SELFCHECKS = [
    'tests.domain_and_repo.allegen',
    'tests.domain_and_repo.animal_category',
    'tests.domain_and_repo.breed',
    'tests.domain_and_repo.column_mgr',
    'tests.domain_and_repo.masking',
    'tests.domain_and_repo.pet',
    'tests.domain_and_repo.product_embedding',
    'tests.domain_and_repo.product_master',
    'tests.domain_and_repo.safty',
    'tests.features.db_threads',
    'tests.features.products',
    'tests.query_sample',
    'tests.pipeline.eval_metrics',
]

# 임베딩 모델을 올리거나(수백 MB) DB 에 썼다 지운다. 기본 실행에서 뺀다
SLOW_SELFCHECKS = [
    'tests.features.smoke',
    # AutoTokenizer.from_pretrained 가 pytest 프로세스 안에서만 죽는 환경이 있다(access
    # violation) - `py -m tests.pipeline.chunking` 로 단독 실행하면 멀쩡하다. numpy/pyarrow/
    # tokenizers 네이티브 확장이 pytest 와 얽히는 문제로 보이며, 원인은 pipeline/prep/chunking.py
    # 최상단 주석 참고. 재현되면 pytest 목록에서 빼는 것 말고는 지금 당장 고칠 수 있는 게 없다.
    'tests.pipeline.chunking',
]


def run(module: str):
    """스크립트를 하위프로세스 없이 __main__ 으로 실행한다. assert 가 터지면 그대로 실패다"""
    runpy.run_module(module, run_name='__main__')


@pytest.mark.parametrize('module', SELFCHECKS)
def test_selfcheck(module):
    run(module)


@pytest.mark.slow
@pytest.mark.parametrize('module', SLOW_SELFCHECKS)
def test_selfcheck_slow(module):
    run(module)
