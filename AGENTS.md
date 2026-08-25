# AGENTS.md

<!-- agents.md 공개 스펙 파일. Claude Code 외 다른 AI 코딩 도구(Cursor, Codex, Aider, Gemini CLI 등)도 이 파일을 읽는다.
     이 저장소에서는 "도구 무관 공통 지침"만 여기 쓰고, Claude Code 전용 사항은 CLAUDE.md에 남긴다. -->

## Project overview

> 반려동물 추천 서비스 "우리 뭐먹냥"의 더미데이터 + RAG 파이프라인 저장소. 
DB가 두 갈래로 나뉜다: pet_reco.db (실제 데이터가 적재되고 파이프라인이 돌아가는 활성 트랙), user.db (src/make_db/create_db_schema.py가 스키마만 짜둔 설계 단계 — 아직 어떤 데이터도 연결 안 됨). 헷갈리지 않게 이 둘을 구분해서 작업할 것.
<!-- 이 저장소가 무엇인지 한두 문단. CLAUDE.md의 "What this repo is"와 겹치지 않게, 도구 무관하게 맞는 사실만. -->

## Setup / commands

> python pipeline/load_db.py      # data/*.csv -> pet_reco.db 적재
> python pipeline/check_data.py   # FK/정합성 검사 (에러 없이 조용히 깨질 수 있어서 필수)
> python pipeline/prepare.py      # 리뷰를 임베딩용 문서로 조립 + 토큰 한도로 자르기 (벡터는 안 만듦)
> python pipeline/build_index.py  # 잘린 chunk를 문장 임베딩 벡터로 변환, chunk_vectors/review_vectors에 저장
> python pipeline/query.py        # 프로필+질문 받아 유사 리뷰 찾는 대화형 CLI (검색 로직 자체는 app/features/retrieve.py)

<!-- 빌드·실행·테스트 명령어. CLAUDE.md의 Commands 섹션을 여기로 옮길지 검토. -->

## Code style

디자인패턴을 준수하고, 파일에서 정해진 역할외에 의존성을 어기지않는 코드 설계를 한다.
함수 인자값에는 자료형을 명시하고 (doc : str), 핵심 주석을 간단 명료하게 작성한다.
코드 네이밍을 규격화하고 모두가 읽기 편한 방식으로 구조를 설계한다.
<!-- 이 저장소에서 지키는 코드 스타일/컨벤션. -->

## Testing instructions

데이터 정합성을 검사하며, 사용자 쿼리에 따른 응답의 질을 높히는 것을 목표로한다.
청킹과 임베드 품질 향상에 중점을 두어 테스트를 통해 개선한다.
<!-- 테스트가 있다면 실행 방법과 통과 기준. -->

## Security considerations

API, Key 등 민감정보가 포함된 데이터는 .env폴더에서 별도로 관리하며, 외부로 노출시키지 않는다.
<!-- 예: selectory.db는 더미 데이터라 민감정보 없음, API 키/자격증명 다루는 부분이 생기면 여기 추가. -->

## Commit / PR guidelines

사용자가 직접 git 에 접근하며, Agent는 Commit, Push는 하지않는다.
<!-- 커밋 메시지 컨벤션(예: 이 repo의 "fix :", "feat :" 접두사 패턴), PR 규칙. -->

## Architecture

> data/*.csv → load_db.py → pet_reco.db → check_data.py(검증) → prepare.py(청킹) → build_index.py(임베딩) → chunk_vectors/review_vectors 테이블 → query.py/app/features/retrieve.py(검색). app/core/db.py가 DB 접근을 전부 모아둠 — 다른 파일은 from app.core.db import query, one, dicts로만 접근.