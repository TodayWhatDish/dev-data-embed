# docs 폴더 안내

뭐가 뭔지 찾기 어려워서 만든 색인. 파일 성격별로 묶여 있다.

## 지금 참고할 것

- **[`REFERENCES.md`](REFERENCES.md)** — API·인프라·계층 배선 작업 전에 먼저 읽는 참고 프로젝트 목록.
- **[`schema/`](schema/README.md)** — 테이블별 스키마 설명 5파일 + [`TODO.md`](schema/TODO.md)
  (스키마가 강제 못 해서 앱이 책임져야 하는 규칙들).
- **[`measurements.md`](measurements.md)** — 임베딩 모델별 채점 결과 기록 (날짜순 누적).
- **[`design/DESIGN.md`](design/DESIGN.md)**, **[`design/GOAL.md`](design/GOAL.md)** — 설계 배경과
  요구사항. 코드와 어긋나는 부분이 있다고 자체적으로 표시돼 있으니 날짜 먼저 확인.

## 역사적 기록 (현재 상태 설명 아님)

- **[`WORK.md`](WORK.md)** — 작업일지. 날짜별로 "왜 그렇게 결정했나"가 쌓여 있다. 최신이 항상
  맨 아래는 아니라 날짜를 보고 읽는다.
- **`DATAINFO.md`**, **`DATAISSUE.md`** — 옛 4테이블 CSV 스키마 시절 데이터 사전/이슈 기록.
  현재 파이프라인(`gen_seed.py`/`load_csv.py`)은 안 읽는 CSV 기준이라 참고용으로만 남겨둠.

## 발표/부수 자료

- **`deck/`** — 강의안·인터뷰 준비·배포 슬라이드(HTML) + 그 슬라이드의 리팩터링 후보를
  실제 코드와 대조한 [`deck/Refactor.md`](deck/Refactor.md).

## 폴더를 만질 때

- 새 스키마 문서는 `schema/`에, 설계/요구사항 문서는 `design/`에 넣는다 — 최상위에 파일을 바로
  추가하지 않는다.
- 이 폴더 이름은 원래 `docu`였다가 `docs`로 바뀌었는데, `WORK.md`·`DATAINFO.md` 같은 옛 기록엔
  `docu/...` 경로가 그대로 남아 있다. 역사적 기록이라 일부러 안 고쳤다 — 새 글을 쓸 땐 `docs/`로.
