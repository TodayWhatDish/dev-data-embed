# 참고 프로젝트

이 저장소의 구조를 설계할 때 참고하는 외부 프로젝트 목록.

**AI 코딩 도구 지침** — API·인프라·계층 배선 작업을 시작하기 전에 이 파일을 읽고,
아래 경로의 파일을 **직접 열어서** 확인한다. 기억이나 추측으로 대신하지 않는다.
경로는 개발 PC 기준 절대 경로다. 없으면 조용히 건너뛰되, 참고 없이 작업했다는
사실을 사용자에게 알린다.

우선순위: 1번이 주 참고 대상이다. 2번은 1번의 이전 버전이라 충돌하면 1번을 따른다.

---

## 1. rag-project-cleanup (주 참고 대상)

- **경로**: `/Users/jaeseong/rag-project-cleanup`
- **무엇**: 화장품 관리자 대시보드 RAG 서비스. 2번을 계층 분리 기준으로 리팩터링한 버전.
- **왜 여기를 보나**: 이 저장소와 **계층 구성이 같고**(`app/{domain,core,repositories,adapters,features,api}` + `pipeline/`),
  이 저장소에 아직 없는 API 계층이 완성돼 있다.

### 무엇을 볼 것인가

| 주제 | 파일 | 핵심 |
|---|---|---|
| 계층 규칙을 테스트로 강제 | `tests/test_layers.py` | `domain(0) < core(1) < repositories·adapters(2) < features(3) < api(4)`. import 그래프를 AST 로 떠서 역참조를 잡는다 |
| main.py 는 조립만 | `app/main.py` | 42줄. 라우터 모듈을 for 문으로 등록하고 정적 파일을 마운트할 뿐 |
| lifespan 분리 | `app/api/lifespan.py` | 마이그레이션·벡터 워밍업·모델 사전 로드. 실패해도 서버는 뜨고 경고만 남긴다 |
| 공통 의존성 | `app/api/dependencies.py` | `caller`(인증), `guard`(쿼터), `writable`(기능 스위치). 라우터는 여기서만 가져다 쓴다 |
| 예외 → HTTP 변환 | `app/api/errors.py` | `STATUS` 표 하나. features 계층은 `HTTPException` 을 모른다 |
| 라우터 한 파일 | `app/api/routers/health.py` | `APIRouter(tags=[...])`, 모든 라우트에 `response_model`, `/health` 는 무인증 `/ready` 는 503 |
| 스레드별 DB 연결 | `app/core/db.py` | `threading.local()` + WAL + `busy_timeout` + `PRAGMA foreign_keys=ON`. 연결 객체를 밖으로 안 내보낸다 |
| 트랜잭션 | `app/core/db.py` 의 `transaction()` | 깊이 카운터로 중첩 안전. `execute`/`insert` 가 묶음 안이면 커밋을 미룬다 |
| 인증 | `app/core/auth.py` | 서비스 토큰 + `X-User-Id` 를 나눠 검사. `compare_digest` 로 타이밍 누출 차단. 운영에서 기본 토큰이면 뜨기 전에 죽는다 |
| 저장소 팩토리 | `app/repositories/__init__.py` | `get_*_repo()` 안에서 지연 import. 순환 import 를 구조로 막는다 |
| 주석·독스트링 규칙 | `CONVENTIONS.md` | 파일 맨 위 한 줄 docstring, 함수 위 `#` 한 줄. 함수 docstring 안 씀 |
| 설계 배경 | `ARCHITECTURE.md` | 왜 그렇게 나눴는지. 코드 주석에 안 적고 여기 적는다 |

### 이 저장소와 다른 점 (그대로 옮기면 안 되는 것)

- **인증 모델**: 저쪽은 앞단 서버가 `X-User-Id` 를 넣어 주는 **내부 서비스**다.
  이쪽은 브라우저가 직접 부르므로 구글 로그인 + JWT 에서 `user_id` 를 꺼내야 한다.
  가져올 것은 `Depends(...)` 로 거는 **모양**이지 `caller()` 내용이 아니다.
- **CORS**: 저쪽은 `StaticFiles` 로 화면을 같은 서버에서 주므로 CORS 가 없다.
  이쪽 화면을 따로 띄운다면 CORS 미들웨어가 별도로 필요하다 (2번 프로젝트 참고).
- **도메인 용어**: 저쪽은 화장품/피부타입/고객, 이쪽은 사료/축종/체급/알러지.
  스키마 필드명을 그대로 옮기지 않는다.

---

## 2. axi-rag-deploy (이전 버전, 보조)

- **경로**: `C:\axi-rag-deploy`
- **무엇**: 1번의 리팩터링 이전 버전. 라우트가 `app/main.py` 한 파일(311줄)에 다 있다.
- **1번이 있는데 왜 남기나**: 1번에 없는 것이 두 개 있다.

| 주제 | 파일 | 핵심 |
|---|---|---|
| CORS 설정 | `app/main.py` 상단 | 오리진 목록을 환경변수 `ALLOW_ORIGINS` 로 받는다 |
| 환경변수 문서화 | `.env.example` | 값마다 왜 필요한지 주석을 단다 |

- **베끼면 안 되는 것**: 라우트를 `main.py` 한 파일에 몰아넣은 배치.
  1번이 이미 그걸 고쳤다. 구조는 무조건 1번을 따른다.