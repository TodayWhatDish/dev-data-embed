# TODO

## pytest 기반 품질 검증 (2026-09-04 갱신)

완료:
- [x] 마스킹 품질 self-check — `tests/domain_and_repo/masking.py` (기존, `test_selfchecks.py`의
      `SELFCHECKS`에 이미 포함돼 있었음)
- [x] 임베딩 추천지표(recall@k / MRR / 노이즈밴드) self-check — `tests/pipeline/eval_metrics.py`
      신규 작성, `SELFCHECKS`에 추가. `pytest` 한 번으로 위 두 개가 같이 돈다 (7~8초, 29 passed)
- [x] 청킹 self-check 초안 — `tests/pipeline/chunking.py` 신규 작성 (`build_review_doc` /
      `split_review` / `count_tokens` 검증). 로직은 맞지만 이 개발 PC에서 pytest 프로세스 안에서만
      `AutoTokenizer.from_pretrained` 쪽이 비결정적으로 access violation이 나서 일단
      `SLOW_SELFCHECKS`로 빼둠 (`pytest -m slow`에도 안 잡히게, 필요하면
      `python -m tests.pipeline.chunking`로 단독 실행)
- [x] `pipeline/prep/chunking.py` — `langchain_text_splitters` import 순서 문제(먼저
      `sentence_transformers`를 import해야 죽지 않음) 원인 찾아서 수정

- [x] `python -m eval all --with-llm` (AGENTS.md 2번 항목: golden/ragas_check/format_check) —
      최상위 `eval/` 패키지 신규 작성.
      - `eval/golden.py` + `eval/golden_qa.json` — `answering.verify()`의 LLM 채점(chat_verify)이
        맞는 답/틀린 답을 제대로 가르는지 골든 셋(참/거짓 케이스 각 1개)으로 확인
      - `eval/format_check.py` — `recommending.recommend()`/`Strategy` 구조화 출력이 라이브
        모델 응답에서도 후보 밖 id를 안 지어내는지 확인 (DB 없이 값만 넣음)
      - `eval/ragas_check.py` — faithfulness만 채점(answer_relevancy는 OpenAI 임베딩을 요구해서
        뺌). ragas==0.4.3이 `langchain_community.chat_models.vertexai`(langchain-community
        0.4.2에서 삭제됨)를 무조건 import해서 죽는 것과, claude-sonnet-5가 temperature
        파라미터를 거부해서 죽는 것 둘 다 원인 찾아서 고침(vertexai는 빈 클래스 shim,
        temperature는 `LangchainLLMWrapper(bypass_temperature=True)`) - 실행 결과: 통과 3 / 건너뜀 0 / 실패 0
      - `.vscode/tasks.json`에 "🤖 LLM 품질 검사" 태스크로 등록. 상용 API라 토큰 비용 발생함

남은 일:
- [ ] `tests.pipeline.chunking`을 기본 `pytest` 목록으로 옮기기. numpy 2.4.6 / pandas 3.0.3 /
      pyarrow 24.0.0 조합이 의심스러움 - 버전을 낮춰 고정했을 때도 재현되는지 먼저 확인할 것
- [ ] 대시보드 "검증" 탭 연결 — `dev-web/frontend/public/admin/admin.html`의 `#verifyView`
      (지금 "준비 중입니다" 문구만 있음, `admin.js`의 `switchView()`가 뷰 전환만 함).
      pytest 결과를 JSON으로 저장해서 관리자 인증 붙은 엔드포인트(예: `/api/verify`)로 읽어오게
      만들 것. *구 버전 이 TODO에 있던 `#evalPanel`/`openEvalPanel`/`web/admin.js`는 리팩터링 전
      파일명이라 지금 구조와 안 맞음 - 실제로는 이 `#verifyView`.*
- [ ] recall@k가 기준치 밑으로 떨어지면 fail하는 threshold 테스트. `docs/REFERENCES.md` 1번
      (rag-project-cleanup)의 `tests/test_layers.py`가 구조 규칙을 강제하는 패턴을 지표 강제로
      응용 — 작업 전에 그 파일을 실제로 먼저 열어서 확인할 것 (REFERENCES.md 원칙)
