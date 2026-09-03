"""python -m eval all             -> 지금은 돌릴 게 없다 (LLM 없는 검사는 tests/pytest 쪽)
   python -m eval all --with-llm  -> golden -> format_check -> ragas_check 순서로 실행
"""
import argparse
import importlib
import sys

from eval import SkipCheck

LLM_CHECKS = ['golden', 'format_check', 'ragas_check']


def main():
    parser = argparse.ArgumentParser(prog='python -m eval')
    parser.add_argument('command', choices=['all'])
    parser.add_argument('--with-llm', action='store_true', help='상용 API를 부르는 검사까지 실행')
    args = parser.parse_args()

    if not args.with_llm:
        print('LLM 없는 검사는 여기 없다 (pytest 로 이미 돈다). --with-llm 을 붙여라.')
        return

    failed, skipped = [], []
    for name in LLM_CHECKS:
        print(f'\n=== {name} ===')
        try:
            importlib.import_module(f'eval.{name}').run()
        except SkipCheck as exc:
            skipped.append(name)
            print(f'[SKIP] {name}: {exc}')
        except Exception as exc:
            failed.append(name)
            print(f'[FAIL] {name}: {exc}')

    print(f'\n통과 {len(LLM_CHECKS) - len(failed) - len(skipped)} / 건너뜀 {len(skipped)} / 실패 {len(failed)}')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
