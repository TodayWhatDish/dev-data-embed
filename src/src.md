# src 코드 흐름

> Last updated: 2026-08-17

`data/*.csv`(더미데이터) → `pet_reco.db`(SQLite) → `review_vectors`(임베딩) 까지의 파이프라인.
RAG 추천에 쓸 리뷰 벡터를 만드는 것이 최종 목표다.

```
data/*.csv ──[load_db.py]──> pet_reco.db ──[build_index.py]──> pet_reco.db ──[query.py]──> 검색
                             (4 테이블)                      review_vectors     └ search.py
                                                             embedding_meta
```

파일은 역할로 나뉜다.

| 파일 | 역할 | 성격 |
| --- | --- | --- |
| `config.py` | 경로·모델명·색인 대상 조건 등 공유 설정 | 표준 라이브러리만 |
| `load_db.py` | CSV → SQLite 적재 | 표준 라이브러리만, 즉시 완료 |
| `build_index.py` | 리뷰 → 벡터 색인 생성 | torch 필요, 20초 남짓 |
| `search.py` | 저장된 벡터로 검색 (라이브러리) | 실행 진입점 아님 |
| `query.py` | 대화형 검색 CLI | `search.py` 사용 |

실행 순서는 고정이다. `load_db.py`가 먼저 돌아야 `build_index.py`가 읽을 테이블이 생긴다.

```bash
python src/load_db.py
python src/build_index.py
python src/query.py      # 검색 (색인을 다시 만들지 않는다)
```

VS Code에서는 `.vscode/tasks.json`의 **전체 재구축** 태스크가 앞의 두 개를 순서대로 돌린다.

`load_db.py`를 다시 돌리고 `build_index.py`를 잊으면 `review_vectors`만 옛 데이터를 가리킨 채
남는다. 조인은 `purchase_id`로 조용히 성립하므로 **에러 없이 엉뚱한 리뷰가 검색된다.**
그래서 `search.py`의 `check_freshness()`가 검색을 시작할 때 이를 감지해 경고한다
(아래 "3. search.py" 참고).

모든 스크립트가 `config.py`의 `ROOT = Path(__file__).resolve().parent.parent` 로 프로젝트 루트를
잡기 때문에 어느 디렉토리에서 실행해도 같은 `pet_reco.db`를 바라본다.

---

## 1. load_db.py — CSV 적재

### 흐름

```
SCHEMAS 정의
   │
   ├─ 테이블마다 반복 ──────────────────────────────┐
   │    DROP TABLE                                  │
   │    CREATE TABLE   (SCHEMAS에서 DDL 생성)        │
   │    load_csv()                                  │
   │      ├─ CSV 헤더 == 스키마 컬럼 검증 (다르면 중단) │
   │      ├─ to_sql_value() 로 타입 변환             │
   │      └─ executemany INSERT                     │
   │ ←───────────────────────────────────────────────┘
   │
   ├─ CREATE INDEX (INDEXES)
   └─ commit + 요약 출력
```

### 핵심 포인트

**`SCHEMAS` 가 단일 원천(single source of truth)**
`{테이블명: [(컬럼명, 타입), ...]}` 딕셔너리 하나에서 `CREATE TABLE` 문, `INSERT` 컬럼 목록,
값 타입 변환 규칙이 모두 파생된다. 스키마를 고칠 때 한 곳만 고치면 된다.

**CSV 헤더 검증 (`load_csv`)**
`reader.fieldnames != expected` 이면 즉시 `ValueError`. 실제로 `pet_purchases.csv`가
10 → 17 컬럼으로 갱신됐을 때 이전 코드가 조용히 깨졌던 이력이 있어서 넣은 방어 로직이다.

**타입 변환 (`to_sql_value`)**
`csv.DictReader`는 모든 값을 문자열로 준다. 컬럼 타입에 맞춰 `int`/`float`로 캐스팅한다.
안 하면 `price <= budget` 같은 비교가 사전순으로 동작해서 틀린 결과가 나온다.
빈 문자열은 `None`(NULL)으로 저장한다.

**ID 컬럼 (`ID` 표시용 타입 + `sql_type`)**
CSV의 ID는 `C0001`, `P0001`, `F0182`, `O00001` 처럼 접두어가 붙어 있다.
`SCHEMAS`에서 `ID` / `ID PRIMARY KEY` 로 표시한 컬럼은

- `sql_type()` 이 DDL 로 내보낼 때 `INTEGER` / `INTEGER PRIMARY KEY` 로 바꾸고
- `to_sql_value()` 가 앞쪽 알파벳을 떼어내 정수로 저장한다 (`C0001` → `1`)

접두어는 컬럼명으로 복원 가능하므로 정보 손실은 없다. 네 종류 ID 모두 1부터 시작하는
연속 정수이고 중복이 없어서 변환이 깨끗하다.

SQLite에는 `INT64`/`BIGINT` 라는 별도 타입이 없다. `INTEGER` 가 이미 8바이트(int64)까지 담는다.
그리고 **`INTEGER PRIMARY KEY` 라고 정확히 써야** rowid 별칭이 되어 별도 인덱스 없이
B-tree 직접 조회가 된다. `BIGINT PRIMARY KEY` 로 쓰면 이 최적화가 적용되지 않는다.

**매 실행마다 `DROP TABLE`**
증분 적재가 아니라 전체 재구축이다. 더미데이터가 갱신되면 그냥 다시 돌리면 된다.

### 생성 테이블

| 테이블 | 행 수 | 역할 |
|---|---|---|
| `pet_customers` | 300 | 보호자(회원) 정보 |
| `pet_profiles` | 404 | 반려견 프로필 — 모든 개인화 추천의 입력 |
| `pet_products` | 200 | 사료/간식 상품 |
| `pet_purchases` | 1439 | 구매 이력 + 리뷰 — **RAG 검색 대상** |

`pet_purchases`에는 리뷰 작성 시점의 반려견 상태(`breed`, `size_category`, `age_group`,
`allergy`, `health_condition`)가 비정규화되어 함께 들어있다. 프로필은 시간에 따라 변하지만
리뷰는 "그때 그 강아지"의 이야기여야 하므로, `pet_profiles`를 조인하지 않고 이 값을 쓴다.

`is_holdout = 1` 인 404건은 추천 성능 평가용으로 빼둔 행이다. 색인에 넣으면 평가가 오염된다.

### 인덱스

```
idx_profiles_customer   pet_profiles(customer_id)
idx_purchases_product   pet_purchases(product_id)
idx_purchases_pet       pet_purchases(pet_id)
idx_purchases_filter    pet_purchases(is_holdout, size_category, age_group)
```

마지막 `idx_purchases_filter`가 아래 `search.py`의 "프로필 선필터" 경로를 커버한다.

---

## 2. build_index.py — 리뷰 색인 생성

이름이 `embed.py`가 아닌 이유는, 임베딩이 이 파일의 전부가 아니기 때문이다.
`model.encode()` 한 줄을 빼면 나머지는 조회·조립·저장이고, 질의 임베딩은 `search.py`도 한다.
이 파일을 구별하는 것은 **결과를 DB에 영속화한다**는 점이다.

### 흐름

```
main()
  ├─ fetch_rows()      대상 리뷰 조회 (holdout 제외 + 상품 조인)  → 1439건
  ├─ build_doc()       행마다 임베딩용 문장 조립
  ├─ model.encode()    문장 → 384차원 벡터 (정규화)
  └─ save_vectors()    review_vectors / embedding_meta 저장
```

검색은 이 파일에 없다. `query.py`로 분리되어 있어서, 검색만 확인할 때 색인을 다시 만들지 않는다.

### fetch_rows — 무엇을 색인하는가

`pet_purchases` ⋈ `pet_products` 조인으로 리뷰와 상품 정보를 한 번에 가져온다.

```sql
WHERE p.is_holdout = 0            -- 평가용으로 남겨둔 행 제외 (현재는 전량 0)
  AND p.review IS NOT NULL
  AND TRIM(p.review) <> ''        -- 빈 리뷰 제외
ORDER BY p.purchase_id            -- 재실행 시 순서 고정
```

이 `WHERE` 조건은 `config.py`의 `INDEX_FILTER` 상수다. `search.py`가 "색인 이후 데이터가
바뀌었는지" 판단할 때 **같은 기준**을 봐야 하므로 한 곳에만 적는다.

`cur.row_factory = sqlite3.Row` 를 설정해서 결과를 컬럼명으로 접근한다
(`row['breed']`). 컬럼이 13개라 인덱스 접근은 실수가 나기 쉽다.

### build_doc — 임베딩 품질의 핵심

리뷰 본문만 넣으면 "어떤 강아지가 쓴 후기인지"가 벡터에 담기지 않는다.
그래서 **반려견 컨텍스트 + 상품 컨텍스트 + 리뷰 본문**을 한 문장으로 조립한다.

```
소형견 시니어 비숑프리제, 알레르기 없음, 관절이 약함. 사료/실버사료 네이처독 실버사료 75
(관절 목적, 건식) 별점 2점 후기: 관절에 좋다고 해서 ...
```

`allergy` / `health_condition` 이 NULL인 행은 `'알레르기 없음'`, `'건강 특이사항 없음'`
같은 명시적 한국어로 바꾼다. 빈 문자열로 두면 문장이 어색해져 임베딩이 흔들린다.

### 모델과 벡터

- 모델: `paraphrase-multilingual-MiniLM-L12-v2` (다국어, 한국어 포함)
- 차원: 384
- `normalize_embeddings=True` → 벡터 길이를 1로 맞춘다.
  이후 코사인 유사도를 **내적만으로** 계산할 수 있다 (`matrix @ q`).

**입력 길이 제한이 있다.** 이 모델의 `max_seq_length`는 **128토큰**이고, 넘으면
경고 없이 뒷부분이 잘린다. 실측한 `build_doc()` 결과는 아래와 같다.

| 항목 | 값 |
| --- | --- |
| 토큰 길이 (최소 / 중앙값 / p90 / 최대) | 64 / 99 / 116 / 141 |
| 128토큰 초과 (= 잘림) | 11건 (0.8%) |
| 메타데이터 접두부(`"후기: "` 앞까지) | 중앙값 56, 최대 67 |

메타데이터가 예산의 절반 가까이를 쓰고, 리뷰 본문이 **맨 뒤**에 오므로 넘칠 때
잘려나가는 쪽은 정작 가장 중요한 본문이다. 지금은 0.8%라 방치 가능하지만 여유가 얇다.
리뷰가 길어지는 데이터가 들어오면 메타데이터 문구를 줄이거나 모델을 교체해야 한다.

### save_vectors — 저장 형태

SQLite에는 벡터 타입이 없으므로 `numpy 배열 → list → JSON 문자열`로 저장한다.

```
review_vectors(purchase_id PK, doc, vector)
embedding_meta(key, value)    -- model / dim / count / source
```

`doc`(임베딩에 실제로 들어간 문장)을 함께 저장한다. 검색 결과를 사람이 눈으로 검증할 때와,
LLM에게 근거로 넘길 때 그대로 쓰기 위함이다.

`embedding_meta`는 색인을 **어떤 모델·차원으로, 어떤 상태의 데이터로** 만들었는지 기록한다.
`source`는 `config.py`의 `source_fingerprint()`가 만든 지문(`건수:ID합:리뷰길이합`)이고,
`search.py`가 검색 시작 시 현재 DB와 비교해 재색인 필요를 알린다
(아래 "3. search.py" 참고).

`DROP TABLE` 후 다시 만들고 `executemany`로 일괄 삽입 — 재실행 시 중복 방지.

---

## 3. search.py — 필터 먼저, 벡터 나중

색인과 분리된 **읽기 전용** 모듈이다. 실행 진입점은 `query.py`이고, 이 파일은 라이브러리다.

**벡터 유사도만 쓰면 조건이 지켜지지 않는다.**
질의 `"닭고기 알레르기가 있는 소형견인데 피부 가려움에 괜찮았던 사료"` 의 실제 결과:

```
1) 벡터 유사도만
   O01105 (0.743) 대형견 퍼피 셰퍼드 ...      ← 소형견이 아님
   O00625 (0.733) 중형견 성견 비글 ...        ← 소형견이 아님
   O00815 (0.731) 대형견 성견 셰퍼드 ...      ← 소형견이 아님

2) 프로필 필터 + 벡터 유사도
   O00418 (0.713) 소형견 시니어 비숑프리제 ...
   O00528 (0.698) 소형견 시니어 시츄 ...
```

`build_doc()`에서 체급·견종을 문장에 넣어도 마찬가지다. 임베딩은 "의미적 유사"만 볼 뿐
조건을 **강제하지 못한다**. 알레르기처럼 틀리면 안 되는 조건은 반드시 SQL로 걸러야 한다.

> 위 `O00418` 은 화면 표기다. DB에는 정수 `418` 로 저장되어 있고,
> 출력할 때만 `fmt_purchase_id()` 가 접두어를 붙인다.
> 검색은 정수를 그대로 반환하므로 호출하는 쪽에서 조인에 바로 쓸 수 있다.

그래서 `VectorStore.search(query, where=..., params=...)` 는 이 순서로 동작한다.

```
review_vectors ⋈ pet_purchases  ──WHERE(프로필 조건)──> 후보 축소
                                 ──내적으로 정렬──────> top_k
```

**실제 추천 API도 이 순서(프로필 선필터 → 벡터 랭킹)를 따라야 한다.**
`params`로 값을 바인딩하므로 사용자 입력을 문자열로 이어붙이지 않는다.

### VectorStore — 벡터를 한 번만 읽는다

벡터는 JSON 문자열로 저장되므로 질의마다 다시 읽으면 파싱 비용이 매번 든다.
1439건 × 384차원이면 질의 한 번에 10MB가 넘는 JSON을 다시 파싱하는 셈이다.
그래서 `VectorStore`가 생성 시 전부 메모리에 올리고, 이후 질의에서는 `WHERE`로 걸러진
`purchase_id`만 받아 해당 행을 골라 쓴다. 실측값은 아래와 같다.

| 구간 | 시간 |
| --- | --- |
| `VectorStore` 생성 (모델 로드 + 벡터 1439건 파싱) | 6.3초 (시작 시 1회) |
| 질의 1회 | 0.01 ~ 0.04초 |
| (참고) 분리 전, 질의마다 벡터를 다시 읽던 비용 | 0.157초 |

### check_freshness — 낡은 색인 감지

`load_db.py`를 다시 돌리면 `pet_purchases`가 통째로 새로 만들어진다. 이때
`build_index.py`를 잊으면 `review_vectors`만 옛 데이터를 가리키는데, 조인은 `purchase_id`로
조용히 성립하므로 **에러 없이 엉뚱한 리뷰가 검색된다.**

`VectorStore` 생성 시 `embedding_meta`의 기록과 현재 DB를 비교해 두 가지를 잡는다.

- `model` 불일치 → 벡터 공간이 달라 유사도가 의미를 잃는다
- `source` 지문 불일치 → 색인 이후 대상 데이터가 바뀌었다

검색을 막지는 않고 경고만 한다. 색인이 조금 낡아도 확인용으로는 쓸 만하고,
여기서 중단시키면 데이터를 손보는 중에 아무것도 못 하게 되기 때문이다.
지문은 `건수:ID합:리뷰길이합`이라 **길이가 같은 오타 수정 같은 변경은 놓친다.**
값싼 안전망이지 검증이 아니다.

---

## 알아둘 점

- **최초 실행 시 모델 다운로드**가 발생한다(수백 MB). 이후에는 HF 캐시에서 로드된다.
- 현재 벡터 검색은 1439건 전체를 메모리에 올려 내적하는 **브루트포스** 방식이다.
  인덱스 구조 없이 후보를 전부 훑으므로 정확한 top-k가 보장되는 대신 O(N)이다.
  더미데이터 규모에서는 충분하지만, 데이터가 커지면 FAISS 같은 벡터 인덱스로 교체해야 한다.
  단 ANN 인덱스는 인덱스가 필터 조건을 모르므로, 지금의 "프로필 선필터 → 벡터 랭킹" 순서를
  그대로 쓸 수 없다. 교체할 때 필터 적용 지점을 다시 설계해야 한다.
- **더미데이터 불일치는 2026-08-17 기준 해소됐다.** 이전에 적어둔 두 가지를 재확인한 결과다.
  - `건식사료`인데 `target_food_form='습식'` → **0건.** 데이터 갱신 과정에서 이미 고쳐졌다.
    (`덴탈껌`·`트릿`·`실버사료`에 건식/습식/공용이 섞인 것은 정상이다. 실제로 두 형태가 다 나온다.)
  - 리뷰 본문이 행의 `size_category`와 어긋나던 문제 → **30건을 수정했다.**
    `소형견용 작은 사이즈로 찾다가...`가 중형/대형 행에(24건), `대형견이라 그런지 사료값이...`가
    소형/중형 행에(6건) 쓰이고 있었다. 행의 실제 체급에 맞는 문구로 바꿨다.

  단, `크기가 적당해서 소형견도 먹기 편해요` 같은 문장은 **모순이 아니라서 두었다.** 대형견
  주인이 상품을 일반적으로 평한 말이지 자기 개가 소형견이라는 뜻이 아니다. 실제 리뷰에도 흔하다.

  > 생성 스크립트가 저장소에 없어 `data/*.csv`를 직접 고쳤다. 더미데이터를 다시 생성하면
  > 같은 문제가 재발한다. 체급 자기지칭 문장은 행의 `size_category`에 맞춰 뽑아야 한다.
- 모델 교체를 검토한다면 `intfloat/multilingual-e5-small`이 한국어 검색 품질은 대체로 낫고
  입력 한도도 512토큰이라 위의 잘림 문제까지 해소된다. 다만 `query:` / `passage:` 접두어
  규약을 지켜야 성능이 나오므로 `build_doc()`과 `VectorStore.search()`를 함께 고쳐야 한다.
  모델을 바꾸면 `check_freshness()`가 불일치를 잡아내므로 재색인을 잊을 일은 없다.
