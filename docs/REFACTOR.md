# dev-data-embed 리팩토링 체크리스트

> 기준일: 2026-09-24 · 대상: `app/` (FastAPI + SQLAlchemy + Supabase Postgres/pgvector), `pipeline/`, `eval/`, `tests/`
> 사용법: 끝낸 항목은 `[ ]` → `[x]`, 요약표 숫자 갱신. 커밋 메시지에 ID를 넣는다 (`fix(BE-01): ...`).
> "완료 기준"은 *어떻게 확인했는지*다. 확인 못 했으면 체크하지 않는다.
> 프론트엔드 체크리스트: `dev-web/docs/REFACTOR.md` (FE-xx)

## 진행 현황

| 우선순위 | 의미 | 완료 / 전체 |
|---------|------|------------|
| P0 | 버그 · 보안 · 운영 장애 | 3 / 16 |
| P1 | 구조 (계층 · 책임 분리) | 8 / 20 |
| P2 | 코드 품질 · 정리 | 0 / 19 |
| P3 | 문서 · 도구 · 배포 | 0 / 11 |

**담당:** P0는 별도 담당자가 맡는다 (크리티컬 항목은 GitHub 이슈로 추적 — 아래 표의 `#번호`). P1부터는 이 체크리스트 순서대로 진행한다.

**작업 순서:**
- P0 담당: BE-03~06 (DB 세션을 요청 단위로, #14) → BE-09 (#18) → BE-10 (#15) → BE-12 (#16) → BE-14 (#17) → 나머지 P0
- P1 이후: BE-21 (공통 예외) → BE-22~24 (계층 정리) → BE-26~29 → 나머지 P1 → P2 → P3
- **P0에 의존하는 P1:** BE-25와 BE-30은 BE-03(`app.state.con` 제거)과 같은 파일을 건드리고, BE-36(커밋 위치)은 BE-04의 세션 수명이 정해져야 한다. 셋 다 P0 담당 작업이 머지된 뒤에 한다.

---

## P0 — 버그 · 보안 · 운영 장애

| ID | 상태 | 위치 | 문제 | 수정 방법 | 완료 기준 |
|----|------|------|------|----------|----------|
| BE-01 | [x] | `app/core/config.py:208`, `app/services/admin_auth.py:15` | `ADMIN_PASSWORD` 기본값이 `""`이고 `compare_digest("", "")`가 True라서, env가 없으면 빈 비밀번호로 관리자 로그인이 됨 | 기동 시 비어 있으면 `RuntimeError` | env 없이 기동하면 서버가 뜨지 않음 |
| BE-02 | [x] | `app/core/config.py:205` | `JWT_SECRET` 기본값이 `""`라 누구나 토큰을 위조할 수 있음 | 비어 있거나 32자 미만이면 기동 실패 | 짧은 키로 기동하면 서버가 뜨지 않음 |
| BE-03 | [ ] | `app/api/lifespan.py:54`, `app/services/searching.py` | `app.state.con` 커넥션 하나를 스레드 40개가 동시에 씀 (스레드 안전하지 않음, 트랜잭션이 계속 열려 있음) | 요청마다 `with engine.connect()` 또는 `get_db` 의존성, `app.state.con` 삭제 | `grep "app.state.con"` 0건, 동시 요청 부하 테스트 통과 |
| BE-04 | [ ] | `app/core/db.py:33` | `scoped_session`을 닫지 않음. 요청이 끝나도 idle-in-transaction으로 커넥션을 붙잡고, 요청 사이에 오래된 데이터가 남음 | `api/deps.py`의 `get_db()` yield 의존성 (commit / rollback / close) | Supabase에서 `pg_stat_activity`에 idle in transaction 0건 |
| BE-05 | [ ] | `app/core/db.py:24` | 커넥션 풀 설정이 없음 (기본 5+10 < 스레드 40), `pool_pre_ping`도 없음 | `pool_size`, `max_overflow`, `pool_pre_ping=True`, `pool_recycle=300` | 오래 방치한 뒤 첫 요청도 성공 |
| BE-06 | [ ] | `app/core/db.py:117-128` | `execute()`는 `_exec_driver_sql`을 거치지 않아 실패해도 롤백하지 않음. `lastrowid`는 sqlite 잔재 | `_exec_driver_sql`로 돌리고 `rowcount` 반환 | 실패한 DELETE 다음 요청이 정상 동작 |
| BE-07 | [ ] | `app/api/routes/auth.py:46-49, 88-92` | `/allergens` 라우트가 같은 함수명으로 두 번 등록됨 | 하나 삭제 | `/docs`에 `/allergens`가 1개 |
| BE-08 | [ ] | `app/core/embedder.py:67` | 요청 처리 중에 키가 없으면 `raise SystemExit`으로 워커 스레드가 죽음 | `RuntimeError`로 바꾸고 키 검사는 기동 시점으로 이동 | `grep SystemExit app/` 0건 |
| BE-09 | [ ] | `app/api/routes/ask.py:84, 100` | `f"LLM 응답 실패: {e}"`로 내부 예외 원문을 클라이언트에 노출 | 고정 문구만 보내고, 원문은 `logger.exception`으로 기록 | LLM 키를 깨뜨렸을 때 응답에 스택이나 키 정보가 없음 |
| BE-10 | [ ] | `/login`, `/admin/login`, `/ask` | 요청 횟수 제한이 없어 무차별 대입이 가능하고 LLM 비용 상한도 없음 | slowapi 등으로 IP별 요청 제한 | 짧은 시간에 연속 로그인하면 429 |
| BE-11 | [ ] | `app/main.py:44` | Bearer 인증인데 `allow_credentials=True`와 `*` 메서드/헤더를 씀 | `allow_credentials=False`, 메서드와 헤더를 명시 | 프론트엔드 전체 기능이 정상 동작 |
| BE-12 | [ ] | `app/services/auth.py:53-57`, `app/repositories/pet.py:127-130` | 가입 시 user, pet, 알러지를 따로 커밋해서 중간에 실패하면 반쪽 데이터가 남음. 이메일 중복 검사에 경쟁 조건이 있음 | 트랜잭션 1개로 묶고, 중복은 unique 제약 위반으로 판정 | 알러지 insert를 일부러 실패시키면 user 행도 없음 |
| BE-13 | [ ] | `app/services/retrieve.py:141-142` | 검색할 때마다 `check_freshness` 쿼리 2개를 더 돌리고 결과를 `print` | lifespan에서 한 번만 확인하고 logger로 기록 | 검색 1회당 쿼리 수 감소, `print` 0건 |
| BE-14 | [ ] | `app/core/trace.py`, `app/api/routes/questions.py`, `app/query.py:27` | 고객 질문을 로컬 jsonl에 저장해서 Railway 재배포 시 사라짐. 락 없이 append하고, query.py가 jsonl 형식을 깨뜨림 | `customer_question` 테이블로 이동 | 재배포 후에도 관리자 질문 목록이 유지됨 |
| BE-15 | [ ] | `Dockerfile:33`, `app/core/auth.py:39` | shell-form CMD라 SIGTERM을 받지 못하고 root로 실행됨. `get_current_admin`은 `-> int`인데 None을 반환하고, 권한이 틀려도 401을 줌 | `${PORT}` 치환 때문에 shell-form은 유지하고 `CMD exec uvicorn ...`처럼 `exec`를 붙임. `USER app`, `--proxy-headers`. 반환 타입을 고치고 권한 불일치는 403 | 컨테이너가 즉시 종료되고, user 토큰으로 admin API를 부르면 403 |
| BE-16 | [x] | `app/services/admin_auth.py:15` | `compare_digest(str, str)`는 비ASCII 문자가 있으면 `TypeError`를 던짐. 한글 비밀번호를 보내면 401이 아니라 500 | `compare_digest(password.encode(), ADMIN_PASSWORD.encode())` | `{"password": "한글"}`로 로그인하면 401 |

> BE-01·02: `lifespan.check_secrets()`로 처리함 (`52e7cb1`). 코드 리뷰로 확인했고, 빈 env로 실제 기동해 보는 확인은 아직 하지 않았다.
> 이슈: BE-03~06 → [#14](https://github.com/TodayWhatDish/dev-data-embed/issues/14) · BE-10 → [#15](https://github.com/TodayWhatDish/dev-data-embed/issues/15) · BE-12 → [#16](https://github.com/TodayWhatDish/dev-data-embed/issues/16) · BE-14 → [#17](https://github.com/TodayWhatDish/dev-data-embed/issues/17) · BE-09 → [#18](https://github.com/TodayWhatDish/dev-data-embed/issues/18). 나머지 P0는 작아서 체크리스트로만 관리한다.

## P1 — 구조 (계층 · 책임 분리)

| ID | 상태 | 위치 | 문제 | 수정 방법 | 완료 기준 |
|----|------|------|------|----------|----------|
| BE-21 | [x] | `app/api/errors.py`, `routes/auth.py:40,56`, `routes/products.py`, `services/products.py:45-50,82-86,118-122` | 예외를 HTTP로 바꾸는 매핑이 products에만 있음. 나머지는 ValueError를 제각각 변환하고 try/except가 반복됨 | `core/exceptions.py`의 `AppError`(NotFound/Conflict/Invalid/Unauthorized)와 `app.add_exception_handler` 1개 | `grep "except (ValueError\|products.ProductError)" app/api` 0건, `ProductError` 정의 0건 (ask·background·health의 try는 BE-22·38 몫) |
| BE-22 | [ ] | `app/api/routes/ask.py:35-103` | 질문 처리 흐름 조립(프로필, 후보, 상세, 로그, 검증)이 라우트 안에 있음 | `services/answering.ask_stream()`으로 옮기고 라우트는 감싸기만 함 | `ask.py` 40줄 이하 |
| BE-23 | [ ] | `ask.py:29-30`, `auth.py:14`, `recommend.py:14`, `customers.py:11` | 라우트가 repository를 직접 import함 | 서비스를 경유하게 하고 `tests/test_layers.py`에 api→repositories 금지 규칙 추가 | test_layers 통과 |
| BE-24 | [ ] | `ask.py:116-117`, `recommend.py:36-40`, `services/purchases.py:17-19` | "첫 번째 펫" 로직이 세 곳에 중복됨 | `services/pets.primary_pet(user_id)` 하나로 | 정의가 1곳 |
| BE-25 | [ ] | `lifespan.py:22`, `services/searching.py:21` | app이 `pipeline.vector_db`를 import함 (그래서 test_layers에 예외 처리가 있고, Dockerfile이 pipeline을 복사함) | `connect()`를 `core/db`로 이동, test_layers의 예외 삭제 | `grep "from pipeline" app/` 0건 |
| BE-26 | [ ] | `app/core/auth.py` | core가 fastapi를 import함 | `api/deps.py`로 옮기고 `HTTPBearer` 사용 (Swagger에 인증 버튼이 생김) | `/docs`에 Authorize 버튼 |
| BE-27 | [x] | `app/core/security.py`, `services/auth.py:25-32`, `services/admin_auth.py:18` | PBKDF2 해시는 한 번도 쓰이지 않고, 토큰 발급 코드가 두 곳에 중복됨 | `security.py`에 bcrypt 해싱과 `create_access_token(sub, role)`을 모음 | `jwt.encode` 호출이 1곳 |
| BE-28 | [x] | `app/core/config.py:27-56, 118, 162` | `.env` 로더를 직접 짰고, import 시점에 `SystemExit`과 `print`가 있음 | pydantic-settings `BaseSettings`로 교체 | 타입이 틀린 env는 기동 시 명확한 에러 |
| BE-29 | [x] | `app/core/config.py:144-158` | 설정 파일에 SQL 조각(INDEX_FILTER, SIZE_CASE)이 있음 | `repositories/vector.py`로 이동 | config.py에 SQL 0건 |
| BE-30 | [ ] | `services/retrieve.py`, `services/searching.py:37-50` | 이름이 헷갈리고, service에 SQL이 있고, `owns_con` 분기가 있고, 없는 파일을 가리키는 docstring이 있음 | `services/search.py`와 `repositories/vector.py`로 정리하고 커넥션은 항상 주입받음 | services에 `text(` 0건 |
| BE-31 | [ ] | `domain/common.py:124`, `domain/products.py:164`, `domain/pet.py:92`, `domain/domain_init.py` | `get_inst()` 싱글톤 전역 캐시 (`== None`, 속성을 `__init__` 밖에서 설정) | lifespan에서 `MasterCache` dataclass를 만들어 `app.state`에 둠 | `get_inst` 0건 |
| BE-32 | [x] | `adapters/stores/llm.py:48-73`, `services/answering.py:20` | import만 해도 LLM 클라이언트 3개와 체인이 생성됨 (키가 필요) | `@lru_cache` 팩토리 함수 | 키 없이 `import app.services.answering` 성공 |
| BE-33 | [x] | `app/adapters/stores/`, `app/domain/port.py:36-75` | stores에 llm.py가 섞여 있음. 구현이 하나뿐인 팩토리, 아무 데도 안 쓰는 ProductRepository Protocol | `adapters/llm.py`, `adapters/vector_store.py`로 평평하게. 안 쓰는 Protocol 삭제 | `adapters/stores/` 없음 |
| BE-34 | [x] | `app/domain/embedding_text.py` | domain이 core.config를 import함 (계층 규칙 위반인데 테스트가 잡지 못함) | 접두어를 인자로 받고 test_layers에 domain→core 규칙 추가 | test_layers 통과 |
| BE-35 | [ ] | `services/embedding_sync.py`, `services/metric/sqlbench.py`, `domain/petcalc.py`, `app/query.py` | 서버가 쓰지 않는 CLI/파이프라인 코드가 app 안에 있음 | `pipeline/`, `scripts/`, `tests/bench/`로 이동 | app/에서 `__main__` 0건 |
| BE-36 | [ ] | `repositories/*` (`commit("product")` 등) | repository가 커밋을 함 (트랜잭션 경계가 잘못된 층에 있음) | 커밋은 `get_db` 또는 service가 함 | repositories에 `commit(` 0건 |
| BE-37 | [ ] | `models/user.py:8`, `product.py:8`, `pet.py:8`, `repositories/purchases.py:69,86` | 시간을 Text로 저장하고 NOW 상수가 3곳에 중복됨. 불리언이 Integer이고 `datetime.now()`는 로컬 시각 | `DateTime(timezone=True)`, `server_default=func.now()`, `Boolean`으로 마이그레이션 | 새 행의 시각이 UTC timestamptz |
| BE-38 | [ ] | `app/api/routes/background.py:10` | 페이지를 열 때마다 Unsplash를 동기로 호출하고 캐시가 없음 (api 층에서 외부 HTTP 호출) | `adapters/unsplash.py`와 TTL 캐시 | 연속 호출해도 외부 요청은 1회 |
| BE-39 | [x] | `app/api/routes/health.py:32`, `app/main.py:64-67` | `/health`가 두 번 정의됨. `/ready`는 준비가 안 돼도 200을 줌 | main의 `/health` 삭제, `/ready`는 준비 안 됨이면 503 | DB를 끊으면 `/ready`가 503 |
| BE-40 | [ ] | 라우터 전반 | 경로가 일관되지 않음 (`/api/customers`와 `/admin/products`) | `APIRouter(prefix=..., tags=...)`로 통일 (FE와 같이 바꿈) | `/docs`의 경로 규칙이 하나 |

## P2 — 코드 품질 · 정리

| ID | 상태 | 위치 | 문제 | 수정 방법 | 완료 기준 |
|----|------|------|------|----------|----------|
| BE-41 | [ ] | `app/main.py` | 헤더 중복, 필요 없어진 torch 세그폴트 우회 import(22행), import 사이에 낀 `init_logger` | `create_app()`에 title/version과 핸들러 등록 | main.py 30줄 이하 |
| BE-42 | [ ] | `app/api/schemas.py` | 파일 하나에 스키마가 몰려 있음. email/date/gender가 `str`, 불리언이 int, 옛 `/search` 설명, `Pick`이 prompting.py와 중복 | `schemas/` 리소스별로 분리, `EmailStr`, `date`, `Literal`, `bool` 사용 | 잘못된 이메일을 보내면 422 |
| BE-43 | [ ] | `/me/profile`, `/me/recommend`, customers | `response_model`이 없음 | 응답 모델 추가 | `/docs`에 응답 스키마가 보임 |
| BE-44 | [ ] | `routes/products.py:16`, `repositories/products.py:88-111` | page/size 검증을 repository에서 함 | `Query(ge=0, le=100)` | `size=0`이면 422 |
| BE-45 | [ ] | `ask.py:109`, `ask.py`의 `json.dumps` 8곳 | `model_dump()`가 모르는 키까지 넘겨 매번 경고가 뜸. 이벤트 생성 코드가 반복됨 | `model_dump(include=...)`, `_event(type, **kw)` 헬퍼 | 경고 로그 0건 |
| BE-46 | [ ] | `services/recommending.py:17,27`, `services/strategy.py:24`, `routes/recommend.py:26` | 튜플을 반환하고, 광범위한 except를 쓰고, LLM 실패를 처리하지 않음. 후보가 없으면 404 | dataclass 반환과 명시적 예외, 후보 없음은 200과 빈 결과 | 후보 없는 회원 → 200 `[]` |
| BE-47 | [ ] | `app/services/auth.py:35-51` | kwargs 15개, `DOG_CATEGORY_ID` 매직값, 비밀번호 정책 없음 | SignupRequest를 통째로 받고 최소 길이 검증 | 짧은 비밀번호는 422 |
| BE-48 | [ ] | lifespan, searching, retrieve, profile, products, customers, domain_init, repositories | `logging.getLogger()` 루트 로거와 f-string 로그 | `getLogger(__name__)`와 `%s` 인자, ruff 규칙 G004 | ruff G 규칙 통과 |
| BE-49 | [ ] | `app/app_logger/logger.py`, `config.py:15,23` | 기본값 DEBUG, 기동할 때마다 로컬 파일을 덮어씀, 주석 처리된 코드, `log/`와 `logs/` 이중 폴더, `DB_PATH` sqlite 잔재 | `core/logging.py`에서 dictConfig로 stdout 출력 (prod는 JSON) | Railway 로그에서 요청 로그가 보임 |
| BE-50 | [ ] | `repositories/products.py:21-35,57-79,91` | 주석 처리된 코드, sqlite 주석, 안 쓰는 함수(`get_product_nutritions` 등) | 삭제 | 참조 0건 확인 후 삭제 |
| BE-51 | [ ] | `repositories/purchases.py:16-28,98-107` | 안 쓰는 함수, IN 목록을 f-string으로 조립함 | 삭제, `= ANY(%s)` | f-string SQL 0건 |
| BE-52 | [ ] | `repositories/pet.py:20-30,94-146` | `str = None` 힌트, f-string WHERE, CommonMgr와 중복, 죽은 코드 | `Optional`과 `select()`, 죽은 코드 삭제 | 같음 |
| BE-53 | [ ] | `repositories/users.py:43` | `list_users`에 페이지네이션이 없고 상관 서브쿼리를 씀 | JOIN/GROUP BY와 limit/offset | 고객 목록 쿼리 1회 |
| BE-54 | [ ] | `services/retrieve.py:146` | 벡터를 문자열 이어 붙이기로 만듦 | `pgvector.sqlalchemy.Vector`로 바인딩 | 문자열 조립 0건 |
| BE-55 | [ ] | `services/products.py:70-98` | 검사가 중복되고, 한 곳에서만 쓰는 함수가 있고, create의 FK 위반이 500이 됨 | 하나로 합치고 BE-21 예외 사용 | 없는 카테고리로 생성하면 400 |
| BE-56 | [ ] | `domain/safty.py`(파일명과 30,64,73행), `domain/common.py`(allegen), `routes/products.py:32`, `api/errors.py:1` | 오탈자 | `safety.py` 등으로 수정 | `grep -i "safty\|allegen\|allregen\|ingrement"` 0건 |
| BE-57 | [ ] | `domain/masking.py:87-97,129`, `domain/port.py:2`, `domain/petcalc.py:3` | 죽은 salt 코드, "[아직 검수 안된 코드]"와 "[클로드 임시 코드]" 표식 | 삭제하거나 검수 | 표식 0건 |
| BE-58 | [ ] | `app/fake_main.py`, 루트 `__init__.py` | 죽은 파일 | 삭제 | 없음 |
| BE-59 | [ ] | 거의 모든 파일 상단, `db.py`, `config.py:47-71`, lifespan, retrieve, masking | "Last Updated" 헤더(중복 포함)와 긴 설명 주석 (sqlite 시절 내용 포함) | 헤더 삭제(git이 할 일), 주석은 이유 1-2줄만 남기고 배경은 docs로 | `grep -ri "last updated" app/` 0건 |

## P3 — 문서 · 도구 · 배포

| ID | 상태 | 위치 | 문제 | 수정 방법 | 완료 기준 |
|----|------|------|------|----------|----------|
| BE-61 | [ ] | git 추적 파일 | `sqlite3.exe`(4MB), `.DS_Store`, `logs/`, `.serena/`, `.vscode/`, egg-info, `hooks/pre-commit.sample`이 커밋돼 있음 | `git rm --cached`하고 `.gitignore`에 추가 | `git ls-files`에 없음 |
| BE-62 | [ ] | `.env` | 값이 빈 템플릿이지만 `.env`라는 이름으로 추적됨 (나중에 실수로 실제 키가 커밋될 위험) | `.env.example`로 이름 변경, `.env`는 gitignore | `.env`가 추적되지 않음 |
| BE-63 | [ ] | `pyproject.toml` | 버전 고정과 lockfile이 없고, `requires-python` 없음, `langchain`을 통째로 씀, requests와 httpx 중복 | `uv lock`, 버전 범위 지정, 쓰지 않는 의존성 제거 | `uv.lock`이 커밋됨 |
| BE-64 | [ ] | `pyproject.toml:72` | ruff 규칙이 E/F/I뿐, 타입 검사 없음 | B, UP, SIM, G, ASYNC 추가, pyright 추가 | `ruff check` 통과 |
| BE-65 | [ ] | `.github/workflows/` | CI가 AI 이슈 요약기 하나뿐 | ruff와 pytest 워크플로 추가 | PR에서 CI가 녹색 |
| BE-66 | [ ] | `tests/test_layers.py:19-32`, `tests/` | 계층 규칙에 예외 2건이 있고 검사 범위가 좁음. API 테스트가 없음. Postgres에서 깨지는 `?` 자리표시자가 남음 (`signup_repo.py:33`, `smoke.py:171`, `incremental_embed.py:62-70`, `bench/master_join.py:67`) | 규칙 추가, `tests/api/`에 TestClient 테스트, `%s`로 수정 | `pytest` 통과, API 테스트 5개 이상 |
| BE-67 | [ ] | `pipeline/prep_rec.py`, `verify.py:21-27`, `prep/*`, `create_schema/*`, `eval/golden.py`, `qa_check.py`, `ragas_check.py`, `tracing.py` | Postgres로 옮긴 뒤 sqlite 잔재가 남아 모듈이 죽었거나 깨짐 | Postgres로 이관하거나 삭제 | 각 모듈 `--help`나 실행 1회 성공 |
| BE-68 | [ ] | `eval/golden_qa.json`, `eval/qa_golden.json`, `pipeline/make_data/gen_seed.py:42-43` | golden 파일이 두 개, 경로를 다시 정의함 | 하나로 합치고 config를 import | golden 파일 1개 |
| BE-69 | [ ] | `Dockerfile` | 버전 고정과 lock이 없고 single-stage, pyproject만 복사하고 `pip install .` | uv lock 설치와 multi-stage | 이미지 크기가 줄고 재빌드 결과가 같음 |
| BE-70 | [ ] | `docker-compose.yml` | 원격 PG를 쓰는데 `./data` 볼륨이 남아 있고, web 빌드 경로가 틀림 (FE-09와 같은 문제) | 볼륨 삭제, web 서비스는 FE-28 결정에 따름 | `docker compose config` 통과 |
| BE-71 | [ ] | `CLAUDE.md`, `AGENTS.md`, `ISSUE.md`, `TODO.md` | features/, sqlite_store, threading.local, 옛 스크립트 이름, 제품명 오기("우리 뭐먹냥") | 현재 구조로 다시 씀, ISSUE/TODO는 이 문서나 GitHub Issues로 합침 | 문서 속 경로가 모두 실제로 존재 |

---

## 목표 구조

```
app/
  main.py                 # create_app(): 미들웨어 · 라우터 · 예외 핸들러 등록만
  core/                   # 어디서나 쓰는 기반 (fastapi를 모름)
    config.py             # pydantic-settings, 필수값은 기동 시 검증
    db.py                 # engine(pool) · SessionLocal
    security.py           # bcrypt + create_access_token
    exceptions.py         # AppError 계층
    logging.py
  api/                    # HTTP만 담당
    deps.py               # get_db · current_user · current_admin
    errors.py             # AppError → HTTP 상태
    routers/              # auth admin_auth products customers purchases ask recommend health background questions
    schemas/              # 리소스별 요청·응답 모델
  services/               # 업무 규칙 (HTTP도 SQL도 모름)
  repositories/           # SQL만 (vector.py = pgvector 검색 포함), 커밋하지 않음
  models/                 # ORM
  domain/                 # 순수 규칙: safety masking prompting master_cache
  adapters/               # 외부 서비스: llm.py embedder.py unsplash.py vector_store.py
scripts/                  # query CLI, sqlbench
pipeline/                 # 데이터 적재와 임베딩 (embedding_sync, embedding_text, petcalc 이동)
eval/
tests/  unit/  api/  selfchecks/
```

**의존 방향:** `api → services → repositories/adapters → core`, `domain`은 아무것도 import하지 않음. `tests/test_layers.py`가 이 규칙을 강제한다.
