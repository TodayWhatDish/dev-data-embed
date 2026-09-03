# TODO

## 임베딩 검증 결과 - pytest 기반으로 구현

대시보드에 자리만 만들어뒀다: 상단바 "임베딩 품질" 버튼 → `#evalPanel` (`web/admin.html`) →
지금은 "준비 중입니다" 문구만 있음 (`#evalPanelBody`). 열고 닫는 로직(`openEvalPanel`,
`web/admin.js`)만 있고 fetch/렌더링은 없는 상태.

나중에는 `tests/eval/` 폴더를 만들어 pytest로 검증한 결과를 이 자리에 띄운다.
- 백엔드: `app/api/routes/health.py`에 관리자 인증 붙인 조회 엔드포인트(예: `/api/eval`)를
  다시 추가하고, `tests/eval/`의 pytest 결과(리포트 JSON 등)를 읽어서 반환.
- 프런트: `web/admin.js`의 `openEvalPanel()`에서 그 엔드포인트를 fetch해 `#evalPanelBody`를
  채운다. Chart.js는 이미 CDN으로 로드돼 있어 그래프가 필요하면 바로 쓸 수 있음.

- 참고: `docs/REFERENCES.md` 1번(rag-project-cleanup)의 `tests/test_layers.py` — pytest로
  구조적 규칙(계층 의존성)을 강제하는 패턴을 갖고 있다고 문서에 적혀 있음. `tests/eval/`에서도
  같은 방식으로 recall@k가 기준치 밑으로 떨어지면 테스트가 fail하게 만드는 걸 참고할 것.
- **확인 필요**: `C:\rag-project-cleanup\rag-project-cleanup`, `C:\axi-rag-deploy` 두 경로 다
  이 작업 시점엔 이 환경에 존재하지 않아 직접 못 열어봤다 (docs/REFERENCES.md 원칙상 추측 금지 -
  작업 시작 전에 실제 파일을 먼저 열어서 확인할 것).
- 바뀌면 `app/api/routes/health.py`의 `/api/eval`과 `web/admin.js`의 `loadEvalResults()`도
  새 결과 포맷(pytest 리포트 or 그걸 파싱한 JSON)에 맞춰 같이 고쳐야 한다.
