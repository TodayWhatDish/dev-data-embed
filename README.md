# dev-data-embed

'오늘 뭐먹냥' — 개·고양이 사료·간식 AI 추천 서비스의 **데이터 계층**.
더미 데이터, SQLite 스키마/로더, 임베딩 실험을 담습니다. 애플리케이션·API 코드는 없습니다.

## 문서

| 파일 | 내용 |
|---|---|
| [`docu/GOAL.md`](docu/GOAL.md) | 프로젝트 방향·요구사항. 무엇이 필요한지의 기준 |
| [`docu/schema/`](docu/schema/README.md) | **컬럼 레퍼런스** — 테이블별 컬럼·인덱스·설계 노트 |
| [`docu/DESIGN.md`](docu/DESIGN.md) | DB 스키마 설계 배경 (2026-08-13 기준, 일부 낡음) |
| [`docu/DATAINFO.md`](docu/DATAINFO.md) | 더미 CSV 데이터 사전 (초기 버전 기준) |
| [`docu/WORK.md`](docu/WORK.md) | 작업일지 |

## 실행

스크립트는 상대 경로를 쓰므로 **저장소 루트에서** 실행합니다.

```bash
py src/create_schema/execute_schema.py   # user.db 스키마 생성 (16 테이블 + 2 뷰)
```

`python` 이 아니라 `py` 인 이유: 스키마가 STRICT 테이블을 쓰므로 **SQLite 3.37+** 가 필요합니다.
PATH 의 `python` 이 구버전(3.9 / SQLite 3.35)이면 `malformed database schema` 로 실패합니다.

`user.db`는 생성 결과물입니다. 직접 편집하지 말고 스크립트로 다시 만드세요.

## 스키마 코드 구성

`src/create_schema/` 는 `docu/schema/` 문서 구성과 1:1 로 대응합니다.

| 파일 | 내용 |
|---|---|
| `execute_schema.py` | **진입점.** 아래 모듈에서 DDL 을 모아 순서대로 실행 + 설계 규칙 전문 |
| `common_schema.py` | `animal_categories`, `allergens` (두 도메인이 공유하는 코드표) |
| `user_schema.py` | `users` |
| `pet_schema.py` | `breeds`, `pets`, `pet_breeds`, `pet_allergies` |
| `product_schema.py` | 제품 8테이블 + 뷰 2개 |
