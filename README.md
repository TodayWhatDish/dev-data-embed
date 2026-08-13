# dev-data-embed

'오늘 뭐먹냥' — 반려견 사료·간식 AI 추천 서비스의 **데이터 계층**.
더미 데이터, SQLite 스키마/로더, 임베딩 실험을 담습니다. 애플리케이션·API 코드는 없습니다.

## 문서

| 파일 | 내용 |
|---|---|
| [`docu/GOAL.md`](docu/GOAL.md) | 프로젝트 방향·요구사항. 무엇이 필요한지의 기준 |
| [`docu/DESIGN.md`](docu/DESIGN.md) | DB 스키마 설계 — 테이블 구성, 설계 규칙, 알러지 안전 판정 |
| [`docu/DATAINFO.md`](docu/DATAINFO.md) | 더미 CSV 데이터 사전 (초기 버전 기준) |
| [`docu/WORK.md`](docu/WORK.md) | 작업일지 |

## 실행

스크립트는 상대 경로를 쓰므로 **저장소 루트에서** 실행합니다.

```bash
python src/make_db/create_db_schema.py   # user.db 스키마 생성 (14 테이블 + 4 뷰)
```

`user.db`는 생성 결과물입니다. 직접 편집하지 말고 스크립트로 다시 만드세요.
