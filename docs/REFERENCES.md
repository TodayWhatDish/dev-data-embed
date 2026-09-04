# 참고 프로젝트

이 저장소의 구조를 설계할 때 참고하는 외부 프로젝트 목록.

**AI 코딩 도구 지침** — API·인프라·계층 배선 작업을 시작하기 전에 이 파일을 읽고,
아래 경로의 파일을 **직접 열어서** 확인한다. 기억이나 추측으로 대신하지 않는다.
경로는 개발 PC 기준 절대 경로다. 없으면 조용히 건너뛰되, 참고 없이 작업했다는
사실을 사용자에게 알린다.

우선순위: 1번이 주 참고 대상이다. 2번은 1번의 이전 버전이라 충돌하면 1번을 따른다.
3번은 1번에서 갈라져 나온 **평가 전용** 갈래다. 채점기·추적(`eval/`, LangSmith) 작업일 때만 3번을 본다.

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

---

## 3. eval-test (평가·추적 전용)

- **경로**: `C:\eval-test`
- **무엇**: 1번(`cosmetic-admin`)에 **채점기 패키지 `eval/` 과 LangSmith 추적을 붙인** 갈래.
  앱 계층(`app/`)은 1번과 같으므로 구조는 여기서 배우지 않는다.
- **왜 여기를 보나**: 이쪽 채점기(`eval/`)를 여기서 옮겨 왔다. 러너·골든셋·형식 준수율·
  답변 품질(ragas)·추적의 **모양**이 전부 여기 원본이 있다. 새 채점기를 붙일 때 먼저 본다.
- **지금 이쪽 상태**: `eval/{__main__,tracing,qa_check,golden,format_check,ragas_check,compare}.py`
  가 다 있다. 측정값은 `docs/measurements.md`, 실행 기록은 `data/eval/runs.jsonl`.

### 무엇을 볼 것인가

| 주제 | 파일 | 핵심 |
|---|---|---|
| 채점기 러너 | `eval/__main__.py` | `STEPS` 표 하나에 (이름, 설명, 요금여부, 기본인자, --with-llm 인자). `python -m eval all` 은 **공짜인 것만** 돈다 |
| 골든셋 Q&A | `eval/qa_golden.json` | 질문 + `product_id` + `section` + `keywords`. **전부 DB 실제 문장에서 뽑는다** |
| 골든셋 자가검증 | `eval/qa_check.py:24-38` | 채점 전에 `keywords` 가 그 섹션 원문에 정말 있는지부터 확인한다. 자가 성한지 먼저 본다 |
| 자의 흔들림 | `eval/golden.py:65-77` | 방법을 안 바꾸고 표본만 바꿔 4번 잰다. **이 폭보다 작은 차이는 '개선'이 아니다** |
| 천장(ceiling) | `eval/golden.py:20-32` | 후보 안에 정답이 있는 비율. LLM 이 아무리 잘해도 이걸 못 넘는다 |
| 조건별 A/B | `eval/format_check.py:38` | `예시없음 / 프롬프트만 / 스키마 강제` 세 조건을 같은 표본에 돌려 JSON·스키마 통과율을 나란히 본다 |
| 심판 LLM | `eval/ragas_check.py:97-101` | faithfulness·answer_relevancy·context_precision. **심판마다 LLM 객체를 따로 준다**(공유하면 `n` 이 덮어써져 조용히 틀린 점수가 나온다) |
| 심판 쓸 자격 | `eval/ragas_check.py:43-50` | 구조화 출력이 약한 로컬 모델은 심판으로 안 쓴다. 못 믿을 심판의 숫자는 없느니만 못하다 |
| 추적 배선 | `eval/tracing.py` | `eval_run()` 컨텍스트 매니저 하나. langsmith 가 없거나 꺼져 있으면 **그대로 통과**시켜 채점은 계속 돈다 |
| 채점/운영 분리 | `eval/tracing.py:91` | 채점은 `LANGSMITH_EVAL_PROJECT`, 실제 요청은 별도 프로젝트. 섞으면 서비스 지표가 채점 때문에 망가진다 |
| ragas 트리 분리 | `eval/tracing.py:108-115` | `detached()` 로 부모 run 을 끊는다. 안 끊으면 ragas 가 `IndexError` 로 죽는다 |
| 무거운 의존성 격리 | `pyproject.toml` `[project.optional-dependencies]` | `eval`(ragas) · `trace`(langsmith) · `local` 을 본체에서 뺀다. 서버 돌리는 데 pandas 는 필요 없다 |
| 경계를 CI 로 강제 | `.github/workflows/ci.yml` | `grep` 으로 `features`/`api` 안의 SQL·저장소 직접 import 를 막는다. 테스트보다 싸고 빠르다 |
| 실습 절차서 | `docs/실습-eval-langsmith.md` | 단계마다 **"> 확인"** 문구가 있다. 안 나오면 거기서 멈춘다. 맨 아래 '막혔을 때' 표 |

### 이 저장소와 다른 점 (그대로 옮기면 안 되는 것)

- **골든셋의 정답 모양**: 저쪽은 `product_id` + `section` 하나를 정답으로 못 박는다.
  거긴 상품 상세가 섹션으로 갈려 있어 정답이 딱 하나다. 이쪽은 상품이 200개인데 같은
  조건(관절·건식)을 만족하는 게 수십 개라, 하나만 정답으로 삼으면 맞는 답을 틀렸다고
  세게 된다. 그래서 `qa_golden.json` 은 **정답 집합을 속성(`expect`)으로 적고** DB 로 푼다.
  자가검증도 "낱말이 원문에 있나"가 아니라 "그 조건을 만족하면서 **색인된 리뷰가 있는**
  상품이 있나"를 본다 — 리뷰가 없는 상품은 벡터 검색이 애초에 못 돌려준다.
- **지표 이름**: 저쪽은 `hit@k`, 이쪽 `golden.py` 는 `recall@k` + `mrr` 을 이미 쓴다.
  이름을 바꾸면 `data/eval/*.json` 에 쌓아 둔 이전 모델 결과와 비교가 끊겨서 그대로 뒀다.
  `qa_check.py` 만 `hit@5`·`precision@5` 를 쓰는데, 정답이 집합이라 자가 다르기 때문이다.
- **추적 도구**: 저쪽은 LangSmith 가 있어야 기록이 남는다. 이쪽은 `eval/tracing.py` 가
  **항상** `data/eval/runs.jsonl` 에 한 줄씩 쌓고 LangSmith 는 켜져 있을 때만 함께 보낸다.
  가입 없이도 추이를 볼 수 있어야 하기 때문이다.
- **마스터 캐시**: 저쪽 채점기는 그냥 `app.features` 를 부르면 된다. 이쪽은 `ProductMgr`
  같은 도메인 싱글턴을 서버 기동 때 `lifespan` 이 채운다(`api/lifespan.py:32`). 채점기는
  서버를 안 띄우므로 `warm_domain()` 을 직접 불러야 한다 — 안 부르면 검색 결과를 상품으로
  바꾸는 **마지막 순간에** AttributeError 로 죽는다. 새 채점기를 만들면 이걸 잊지 않는다.
- **ragas 설치**: `ragas 0.4.3` 이 `langchain_community.chat_models.vertexai` 를 무조건
  import 하는데 `langchain-community 0.4.x` 에서 그 모듈이 없어졌다. `pyproject.toml` 의
  `eval` 엑스트라가 `~=0.3.31` 로 묶는 이유다. 이쪽 `app/` 은 `langchain_community` 를
  한 군데도 안 써서 내려도 서버에 영향이 없다.