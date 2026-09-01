# 참고 프로젝트

이 저장소의 구조를 설계할 때 참고하는 외부 프로젝트 목록.

**AI 코딩 도구 지침** — API·인프라·배선 작업을 시작하기 전에 이 파일을 읽고,
아래 경로의 파일을 직접 열어서 확인한다. 기억에 의존해 추측하지 않는다.
경로는 개발 PC 기준 절대 경로다. 다른 환경에서 경로가 없으면 조용히 건너뛰고,
참고 없이 작업했다는 사실을 사용자에게 알린다.

---

## 1. axi-rag-deploy

- **경로**: `C:\axi-rag-deploy`
- **무엇**: 화장품 관리자 대시보드 RAG 서비스.
  이 저장소와 **동일한 계층 구조**(`app/{adapters,core,domain,features}` + `pipeline/` + `eval/`)를 쓴다.
- **참고 이유**: 이 저장소보다 API 계층이 완성돼 있다. 배선 방식을 여기서 가져온다.

### 무엇을 볼 것인가

| 주제 | 파일 | 핵심 |
|---|---|---|
| 스레드별 DB 커넥션 | `app/core/db.py` | `threading.local()` + WAL + `busy_timeout`. 커넥션 객체를 밖으로 안 내보낸다 |
| 읽기/쓰기 함수 분리 | `app/core/db.py` | `query`/`one`/`dicts`(읽기)와 `execute`/`executemany`(쓰기+커밋)를 나눈다 |
| 인증 의존성 | `app/core/auth.py` | `verify_token()` 하나 + 라우트마다 `Depends(verify_token)`. 401 에 `WWW-Authenticate` 헤더 |
| CORS 설정 | `app/main.py` 상단 | 오리진 목록을 환경변수 `ALLOW_ORIGINS` 로 받는다 |
| 도메인 예외 → HTTP | `app/features/products.py` 의 `ProductError` + `app/main.py` 의 `_product_http()` | features 계층은 `HTTPException` 을 모른다. 변환은 API 계층에서만 |
| 응답 스키마 | `app/features/schemas.py`, `app/features/product_schemas.py` | 모든 라우트에 `response_model`. `Page[T]` 제네릭. LLM 출력용 Draft 와 검증용 모델을 분리 |
| 스트리밍 응답 | `app/main.py` 의 `/api/ask` | NDJSON 줄 단위. 사용량은 ContextVar 가 아니라 dict 그릇으로 받는다 |
| 환경변수 문서화 | `.env.example` | 값마다 왜 필요한지 주석 |

### 베끼면 안 되는 것

- **라우트를 `main.py` 한 파일에 몰아넣은 배치.** 저쪽은 단일 사용자라 엔드포인트가 적다.
  이 저장소는 다중 사용자(구글 로그인 → `user` → 사용자별 `pet`)라 엔드포인트가 계속 늘어난다.
  `app/api/routes/` 분리를 유지한다.
- **`.env` 토큰 한 개짜리 인증.** 저쪽 `verify_token()` 은 항상 `"admin"` 을 돌려준다.
  이쪽은 JWT 에서 `user_id` 를 꺼내야 한다. 가져올 것은 `Depends` 로 거는 **모양**이지 내용이 아니다.
- **도메인 용어.** 저쪽은 화장품/피부타입/고객, 이쪽은 사료/축종/체급/알러지.
  스키마 필드명을 그대로 옮기지 않는다.