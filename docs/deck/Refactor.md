## 우리 시스템의 아키텍쳐 드라이버는 이렇다.

아래는 `docs/deck/*.html` 두 강의안에 적힌 리팩토링 후보를 실제 코드와 대조해 검증한 결과다.
이미 커밋으로 해결된 항목(예: config.py 중복, sqlite_store.py 구현, recommending.py 재시도,
repositories/users.py, routes/health.py)은 슬라이드에 남아 있어도 여기서 뺐다.

---

### 1. `app/features/searching.py` → `pipeline` 직접 import (레이어 위반)

- **파일**: `app/features/searching.py:16, 30, 41`
- `from pipeline.vector_db import search, connect` 를 features 계층에서 직접 부른다.
  CLAUDE.md 레이어 규칙(`domain(0) < core(1) < repositories(2)/adapters(2) < features(3) < api(4)`)과
  "앱은 pipeline 없이도 떠야 한다" 원칙에 유일하게 어긋나는 지점.
- 부수 효과: `connect()`가 매 호출마다 새 `sqlite3.connect()`를 열고 `finally`에서 닫는다(23~41행) —
  같은 요청 안에서 `app.core.db.get_con()`(스레드-로컬, 재사용)과 별도의 커넥션을 하나 더 쓰는 셈이라
  연결 관리가 두 갈래로 나뉜다.
- **방향**: `domain/port.py`의 `VectorStore` 계약과 이미 구현체가 있는
  `app/adapters/stores/sqlite_store.py`를 통해 검색을 노출하거나, `search()`를 `app/` 쪽으로 옮긴다.
  옮기면서 커넥션도 `get_con()` 하나로 합쳐진다.

### 2. `candidates()` N+1 조회

- **파일**: `app/features/searching.py:44-55`
- 검색 결과(`hits`) 한 건마다 `purchase_repo.get_product_id()` → `product_repo.find_by_id()`를
  순차 호출한다. `hits`가 `limit`(기본 20)건이면 쿼리가 최대 40번 나간다.
- **방향**: `purchase_id` 목록을 한 번에 모아 product까지 조인한 쿼리 하나로 대체.
  (`repositories/purchases.py` 또는 `products.py`에 `find_products_by_purchase_ids()` 같은
  배치 조회 함수 하나 추가)

### 3. 중복된 HTTP 에러 변환 함수

- **파일**: `app/api/routes/products.py:15-18` vs `app/api/errors.py:10-12`
- `routes/products.py`가 자체 `_http()`를 갖고 있는데, `errors.py`에 이미 같은 일을 하는
  `product_http()`가 있다(둘 다 `ProductError.kind` → `HTTPException` 매핑).
- **방향**: `routes/products.py`의 `_http` 정의(15-18행)를 지우고
  `from app.api.errors import product_http`로 교체, 호출부(33, 50, 58행)의 `_http(exc)`를
  `product_http(exc)`로 변경.

### 4. 죽은 코드 + 저장 형식 불일치: `load_vectors()`

- **파일**: `app/core/db.py:119-136`
- `json.loads(vector)`로 벡터를 읽는데, 실제 벡터 테이블(`chunk_vectors`, `product_vectors`,
  `customer_vectors`)은 전부 `BLOB`(sqlite_vec `serialize_float32`)로 저장돼 있다 — 호출하면
  `json.loads`에서 바로 터진다.
- 게다가 이 함수를 부르는 곳이 코드베이스 어디에도 없다(grep 결과 정의부만 존재).
  실제 벡터 비교는 `pipeline/prep/inspect.py`가 `vec_distance_cosine(v.vector, ?)`로
  BLOB을 직접 쓴다.
- **방향**: 안 쓰는 함수면 삭제, 쓸 계획이 있으면 `sqlite_vec.deserialize_float32`로 다시 짠다.
  `pipeline/prep/verifying.py:75`의 "저장 형식(BLOB vs JSON)을 가리지 않고 읽되" 주석이
  이 불일치를 이미 지목하고 있다.

### 5. 빈 스텁

- `pipeline/prep/matrics.py:9-10` — `calculate_score()` 가 `pass`뿐.
- `pipeline/__main__.py` — 빈 파일.
- 둘 다 실제로 쓸 계획이 없으면 삭제, 쓸 거면 무엇을 계산/실행할지부터 정의.

### 6. README 명령어 최신화

- **파일**: `README.md:34`
- `python -m pipeline.load_db` 로 적혀 있는데 실제 모듈명은 `pipeline.load_csv`
  (AGENTS.md Setup/commands 기준, 이미 리네임됨).
- 같은 섹션(34-37행)에 `pipeline.prep_rec`, `pipeline.verify`, `eval`, `uvicorn app.main:app --reload`
  같은 실제로 쓰는 명령이 아예 빠져 있다 — AGENTS.md의 Setup/commands 블록과 동기화 필요.

---

### 참고: 지금 손 안 대도 되는 것 (설계 의도 확인됨)

- **알러지 판정 3중 정의** — `app/domain/safty.py:4-7` 자체가 "뷰(`pipeline/create_schema/product_schema.py`
  의 `v_product_safety`) · `retrieve.FILTERS['allergy']` · 여기, 셋 다 고친다"고 명시. 세 곳이 하는 일이
  달라서(뷰=전량 선별, FILTERS=SQL 선필터, safty.py=근거 부착) 하나로 합칠 대상이 아니라
  "동기화 잊지 말 것" 체크리스트에 가깝다. 지금처럼 주석으로 상호 참조해두는 선에서 충분.
- **`ponytail:` 표시된 의도적 단순화** — 트리거 조건이 이미 코드에 적혀 있어 지금 손댈 필요 없음:
  `app/core/config.py:151`(VERIFY_MODEL 분리, 로컬 모델 2개 생기면), `app/core/trace.py:76,105`
  (로그 회전/풀스캔, `query_log.jsonl`이 커지면), `app/domain/masking.py:73`(정규식 → NER, 재현율
  필요해지면), `app/features/answering.py:25`(키워드 트리거, 질문 종류 늘어나면).
