# Last Updated: 2026-09-04

"""LLM 이 요청한 형식을 지키나.  python -m eval format_check [표본수] [조건이름 ...]

recommending.recommend() 는 형식이 깨지면 최대 2번까지 다시 부른다(MAX_RETRIES).
그래서 서비스는 멀쩡해 보이는데, 그 재시도가 요금과 응답 시간으로 매번 나가고 있다.
여기서는 재시도를 끄고 첫 응답만 본다 - 재시도가 가리고 있던 실력을 보려는 것이다.

조건 셋을 같은 표본에 돌린다.
    지시만      프롬프트로 "JSON 으로 답하라" 고만 시킨다
    예시추가    거기에 JSON 모양 예시를 하나 붙인다
    스키마 강제  with_structured_output(Recommendation) 로 모델 쪽에 스키마를 건다

셋을 나란히 봐야 "예시 한 줄이 스키마 강제만큼 효과가 있나" 를 답할 수 있다.
스키마를 걸면 JSON 파싱은 공짜로 통과하지만, 후보 밖 product_id 나 개수 오류까지
막아 주지는 않는다 - 그게 이 표에서 실제로 봐야 할 칸이다.

LLM 을 부른다. 표본 하나에 조건 수만큼 호출이 나간다.
"""
import json
import sys
import time

sys.stdout.reconfigure(errors="replace")

from pydantic import ValidationError

from app.adapters.stores.llm import chat
from app.core.config import LLM_MODEL
from app.domain.prompting import Recommendation, build_recommend_prompt
from app.features.searching import candidates as search_candidates
from pipeline.vector_db import connect

from eval.golden import load_holdout
from eval.tracing import banner, eval_run, require_llm, warm_domain

N_PICK = 5

# (이름, 예시를 붙이나, 스키마를 거나)
CONDITIONS = [("지시만", False, False), ("예시추가", True, False), ("스키마 강제", True, True)]

EXAMPLE = '\n예: {"picks": [{"product_id": 12, "reason": "관절 목적 사료라 조건에 맞는다"}]}'
INSTRUCTION = '\npicks 라는 목록에 product_id 와 reason 을 담아 JSON 으로만 답한다. 다른 말은 쓰지 않는다.'


def extract_json(text: str) -> str:
    """모델이 JSON 앞뒤에 덧붙인 것을 걷어낸다.

    ```json 울타리와 "네, 추천해 드릴게요" 같은 인사말이 가장 흔하다. 이걸 안 걷으면
    내용은 멀쩡한데 파싱 실패로 세게 되고, 그러면 고칠 곳을 프롬프트가 아니라 엉뚱한
    데서 찾는다.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        text = text[4:] if text.startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end != -1 else text


def ask_once(cands: list[dict], profile: dict, with_example: bool, force_schema: bool) -> str:
    """조건 하나로 한 번만 부른다. 재시도는 안 한다 - 첫 응답이 이 채점의 대상이다."""
    prompt = build_recommend_prompt(cands, profile, N_PICK) + INSTRUCTION
    if with_example:
        prompt += EXAMPLE

    if not force_schema:
        return chat.invoke(prompt).content or ""

    # include_raw=True 라야 스키마를 걸었을 때도 모델이 실제로 뱉은 것을 볼 수 있다.
    # 프로바이더에 따라 본문이 비고 도구호출 쪽으로만 오는데, 그때는 파싱된 값을 도로
    # JSON 으로 만들어 같은 자로 잰다 - 모델이 형식을 지킨 건 사실이기 때문이다.
    got = chat.with_structured_output(Recommendation, include_raw=True).invoke(prompt)
    raw = got.get("raw")
    if raw is not None and (raw.content or "").strip():
        return raw.content
    parsed = got.get("parsed")
    return json.dumps(parsed.model_dump(), ensure_ascii=False) if parsed is not None else ""


def judge(answer: str, valid_ids: set[int]) -> dict:
    """응답 하나를 다섯 칸으로 접는다. 조건이 달라도 자는 하나여야 비교가 성립한다."""
    out = {"json_ok": False, "n_picks": 0, "out_of_range": 0, "duplicated": False, "schema_ok": False}
    try:
        data = json.loads(extract_json(answer))
    except (json.JSONDecodeError, ValueError):
        return out
    if not isinstance(data, dict):
        return out

    out["json_ok"] = True
    picks = data.get("picks") or []
    numbers = [p.get("product_id") for p in picks if isinstance(p, dict)]
    out["n_picks"] = len(picks)
    out["out_of_range"] = sum(1 for x in numbers if x not in valid_ids)
    out["duplicated"] = len(set(numbers)) != len(numbers)

    try:
        Recommendation.model_validate(data)
        out["schema_ok"] = True
    except ValidationError:
        pass
    return out


def main(argv: list[str]) -> int:
    n = int(argv[0]) if argv and argv[0].isdigit() else 30
    wanted = [c for c in CONDITIONS if len(argv) < 2 or c[0] in argv[1:]]

    banner("LLM 형식 준수 (format_check)")
    if not require_llm():
        return 2
    warm_domain()

    con = connect()
    try:
        sample = load_holdout(con)[:n]
    finally:
        con.close()

    print(f"모델 {LLM_MODEL} · 표본 {len(sample)}건 · 조건 {len(wanted)}개 ({' / '.join(c[0] for c in wanted)})")
    print(f"재시도는 끄고 첫 응답만 본다. 호출 {len(sample) * len(wanted)}번\n")

    with eval_run(
        "format_check",
        inputs={"표본": len(sample), "조건": [c[0] for c in wanted], "n_pick": N_PICK},
        tags=[c[0] for c in wanted],
    ) as run:
        results = {c[0]: [] for c in wanted}
        started = time.perf_counter()

        for i, (_pid, _prod, animal, size, allergy, review) in enumerate(sample, start=1):
            profile = {"animal_category": animal, "size_category": size, "allergy": allergy}
            cands = search_candidates(profile, review)
            if not cands:
                continue
            valid_ids = {c["product_id"] for c in cands}

            for label, with_example, force in wanted:
                try:
                    answer = ask_once(cands, profile, with_example, force)
                except Exception as broke:
                    # 호출 자체가 터진 것도 '형식을 못 지킨 것'으로 센다. 안 세면
                    # 실패한 표본만 조용히 빠져서 성공률이 실제보다 좋아 보인다.
                    print(f"\n  {i}번 [{label}] 호출 실패: {type(broke).__name__}: {broke}")
                    answer = ""
                results[label].append(judge(answer, valid_ids))

            done = time.perf_counter() - started
            print(f"  {i}/{len(sample)}  ({done / i:.0f}초/건 · 남은 시간 {(len(sample) - i) * done / i / 60:.0f}분)", end="\r")

        print(" " * 70, end="\r")
        print("=" * 74)
        print(f"  JSON 파싱  {N_PICK}개를 다 냄  후보 밖 ID  중복  스키마 통과   조건")
        for label, rows in results.items():
            total = len(rows)
            if not total:
                print(f"  {'표본 없음':>50}   {label}")
                continue
            n_numbers = sum(r["n_picks"] for r in rows)
            print(
                f"  {sum(r['json_ok'] for r in rows):>5}/{total:<4}"
                f" {sum(r['n_picks'] == N_PICK for r in rows):>8}/{total:<4}"
                f" {sum(r['out_of_range'] for r in rows):>7}/{n_numbers:<4}"
                f" {sum(r['duplicated'] for r in rows):>5}"
                f" {sum(r['schema_ok'] for r in rows):>8}/{total:<4}   {label}"
            )
            run.record(**{
                f"[{label}] JSON 성공률": round(sum(r["json_ok"] for r in rows) / total * 100, 1),
                f"[{label}] 스키마 통과율": round(sum(r["schema_ok"] for r in rows) / total * 100, 1),
                f"[{label}] 후보 밖 ID": sum(r["out_of_range"] for r in rows),
            })

        print(f"\n총 {time.perf_counter() - started:.0f}초")
        print("이 숫자를 docs/measurements.md 에 잰 날짜·표본과 함께 옮겨 적는다.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
