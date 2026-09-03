# Last Updated: 2026-09-03

"""채점기를 한 자리에서 부른다.  python -m eval all

STEPS 표에 한 줄 넣는 것이 채점기를 붙이는 유일한 절차다. 각 채점기는 자기 파일에서
그냥 __main__ 으로 돌아가므로 러너가 없어도 단독으로 돈다 - 러너는 묶기만 한다.

요금 여부를 표에 박아 두는 이유: 'all' 이 돈을 쓰면 아무도 all 을 못 돌린다.
"""
import runpy
import sys

sys.stdout.reconfigure(errors="replace")

# (모듈명, 설명, 요금이 드나, 기본 인자, --with-llm 일 때 인자)
STEPS = (
    ("golden", "검색이 정답 상품을 찾아오나 (recall@k · MRR · 흔들림)", False, [], ["--llm", "5"]),
)

BY_NAME = {step[0]: step for step in STEPS}


def usage():
    print("사용법:  python -m eval <채점기> [인자]")
    print("         python -m eval all [--with-llm]")
    print()
    for name, what, costs, _args, _llm in STEPS:
        print(f"    {name:<14} {what}{'  (요금)' if costs else ''}")
    print()
    print("  all            요금이 안 드는 것만 돌린다")
    print("  all --with-llm 전부 돌린다. 표본을 작게 잡아도 요금이 나간다")


def run_one(name, args):
    """채점기를 자기 파일처럼(__main__) 돌린다. 죽어도 다음 채점기는 계속 간다."""
    sys.argv = [f"eval/{name}.py", *args]
    try:
        runpy.run_module(f"eval.{name}", run_name="__main__")
        return True
    except SystemExit as stop:
        return stop.code in (0, None)
    except Exception as broke:
        print(f"\n  !! {name} 이 도중에 멈췄다: {type(broke).__name__}: {broke}")
        return False


def run_all(with_llm):
    chosen = [s for s in STEPS if with_llm or not s[2]]
    outcome = {}
    for name, _what, _costs, args, llm_args in chosen:
        print(f"\n{'─' * 74}\n▶ {name}\n{'─' * 74}")
        outcome[name] = run_one(name, llm_args if with_llm else args)

    print(f"\n{'=' * 74}\n요약\n{'=' * 74}")
    for name, ok in outcome.items():
        print(f"  {'○' if ok else '×'}  {name}")
    return 0 if all(outcome.values()) else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        usage()
        return 0
    if argv[0] == "all":
        return run_all(with_llm="--with-llm" in argv)
    if argv[0] not in BY_NAME:
        print(f"모르는 채점기다: {argv[0]}\n")
        usage()
        return 2
    return 0 if run_one(argv[0], argv[1:]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
