LastUpdated : 2026-08-13

# DESIGN.md — DB 스키마 설계

'오늘 뭐먹냥'의 데이터 계층 설계. 구현은 `src/make_db/create_db_schema.py`이며,
테이블마다 `-- Comment:`(용도), 컬럼마다 `-- desc:`(설명)이 달려 있다. **이 문서와 그 파일이 어긋나면 파일이 정답이다.**

```mermaid
flowchart TB
    subgraph L1["1. 데이터 계층 (기존, src/)"]
        CSV["data/*.csv"] --> LOAD["load_db.py"] --> DB[("pet_reco.db\nSQLite")]
        DB --> EMBED["build_index.py"] --> VEC[("review_vectors\n(doc, vector)")]
    end

---

## 1. 설계 규칙

| # | 규칙 | 이유 |
|---|---|---|
| 1 | 모든 PK는 `INTEGER PRIMARY KEY` | SQLite rowid 별칭 — 테이블 B-tree가 정수로 직접 키잉되어 별도 인덱스가 안 생기고, 조인이 문자열 비교가 아닌 64비트 정수 비교가 된다 |
| 2 | 다대다 연결 테이블도 대리키 + 자연키 UNIQUE | 행 하나를 단일 값으로 참조 가능해 API/ORM에서 편하다 |
| 3 | 상태를 저장하지 않고 사실만 저장해 파생 | 휴면 = `last_login_at`에서 계산, 탈퇴 = `withdrawn_at IS NOT NULL`. 정책이 바뀌어도 데이터를 안 고친다 |
| 4 | 날짜/시각은 TEXT ISO-8601 | `'YYYY-MM-DD'`는 사전순 == 시간순이라 문자열 비교만으로 범위 조회·정렬이 성립한다 |
| 5 | 금액은 INTEGER(원 단위) | REAL은 반올림 오차가 생긴다 |
| 6 | 불리언은 INTEGER + `CHECK IN (0,1)` | SQLite에 BOOL이 없다 |
| 7 | 전 테이블 STRICT | 선언한 타입과 다른 값은 INSERT 거부. 끄지 않는다 |

### unsigned 타입에 대해

SQLite에 unsigned 정수 타입은 **없다.** `uint32`/`uint64`는 STRICT에서 `unknown datatype` 에러이고,
비STRICT에서는 통과하지만 INTEGER로 해석될 뿐 음수도 그대로 들어간다.
폭 지정도 무의미하다 — SQLite는 INTEGER를 값 크기에 따라 1~8바이트로 가변 저장한다.

1. **hard constraint는 SQL, soft preference는 벡터.**
   `src/search.py`의 `VectorStore.search()`에서 이미 확인된 사실: 벡터 유사도만으로는 "닭고기 알레르기 소형견" 같은 조건이 지켜지지 않는다(상위 결과가 대형견 리뷰였음, `docu/WORK.md` §3). 알레르기처럼 틀리면 안 되는 조건은 반드시 SQL 선필터를 거친 뒤에만 벡터 랭킹을 적용한다. 검색 계층은 이 순서를 강제하는 것 자체가 존재 이유다.

### 인덱스 원칙

**FK 컬럼에는 건다**(조인과 부모행 삭제 검사에 매번 쓰인다). 나머지는 느린 쿼리를 관측한 뒤 건다.
인덱스는 쓰기 비용과 공간을 항상 지불하고 읽기 이득은 조건부다.

- 날짜 컬럼에 단독 인덱스는 걸지 않는다. 조회가 항상 부모 ID로 먼저 좁혀지므로,
  필요해지면 `(pet_id, purchased_at)` 복합으로 만든다.
- 연결 테이블의 부모 FK에는 인덱스를 따로 만들지 않는다. UNIQUE 인덱스를 `(부모, 자식)` 순서로
  두면 leftmost prefix 규칙에 따라 단일 컬럼 조회에도 그대로 쓰인다.
  실제로 `WHERE pet_id = ?`가 `uq_pet_allergen`을 **COVERING INDEX**로 탄다.

---

## 2. 테이블 (1단계 — 추천 경로)

`docu/WORK.md`의 "남은 과제"가 그대로 이 파이프라인의 리스크다:

- **더미데이터 정합성** — 견종/체형 모순 행 30건을 2026-08-17에 수정해 현재는 0건(`docu/WORK.md` 2026-08-17 §5). 다만 생성 스크립트가 저장소에 없어 CSV를 직접 고친 것이라, 데이터를 재생성하면 재발한다. → 임베딩 전에 검증 스텝 필요(원칙 2와 직결).
- **토큰 잘림** — 현재 모델 한도 128토큰, 문서 평균 97토큰, 3% 잘림. 리뷰가 길어질수록 악화, 결론 문장이 잘리는 경우가 많음.
- **벡터 저장 포맷** — JSON 문자열이라 8.3MB(원래 1.5MB면 될 양). 지금 규모는 무관하나 먼저 손볼 지점으로 기록.

## 5. API 초안

```
users ──< pets ──< pet_allergies >── allergens
           │                            │
           └── breeds                    │
                                        │
products ──< product_ingredients >── ingredients ──┘ (allergen_id)
   ├──< product_feeding_purposes >── feeding_purposes
   └──── product_nutrition (1:1)

users, pets, products ──< purchases ──< reviews ──── review_embeddings (1:1)
```

| 테이블 | 용도 |
|---|---|
| `users` | 보호자 계정. 최상위 소유자 |
| `pets` | 반려견 프로필. 추천의 정형 입력 |
| `breeds` | 견종 마스터 |
| `allergens` | 알러지원 마스터. 반려견과 제품 원료를 잇는 공통 어휘 |
| `pet_allergies` | 반려견별 알러지. **하드 필터의 입력** |
| `feeding_purposes` | 급여목적 마스터 (관절/다이어트/피부) |
| `products` | 판매 제품. 추천 후보 집합의 원본 |
| `product_feeding_purposes` | 제품 ↔ 급여목적 (겸용 제품 표현) |
| `product_nutrition` | 보장성분표. 결측이 많아 1:1 분리 |
| `ingredients` | 원료 마스터. `allergen_id`가 안전 판정의 연결 고리 |
| `product_ingredients` | 제품 ↔ 원료 |
| `purchases` | 구매 이력 |
| `reviews` | 후기. RAG 검색 대상이자 핵심 자산 |
| `review_embeddings` | 후기 벡터 (BLOB) |

### 주요 설계 판단

**`birth_date`를 저장하고 나이는 계산한다.** `age` 정수를 저장하면 시간이 지나면서 조용히 틀려진다.

**`purchases`와 `reviews`를 분리한다.** 후기 없는 구매가 실제로는 다수인데 한 테이블이면 표현할 수 없고,
구매 시점과 작성 시점이 뭉개진다. 급여 2주 뒤 후기와 당일 후기는 신뢰도가 다르다.

**`price_per_100g`는 생성 컬럼이다.** 예산 비교의 실제 기준. 1.8kg 3만원(100g당 1,666원)과
5kg 6만원(100g당 1,200원)은 총액으로 비교하면 순서가 뒤집힌다.

**`pet_allergies`에 심각도를 두지 않는다.** 보호자가 알러지를 안다는 건 이미 겪어봤다는 뜻이므로
무조건 배제한다. 반쯤 아는 심각도로 필터 강도를 조절하는 게 가장 위험하다.
같은 이유로 **리뷰에서 추론한 알러지를 이 테이블에 넣지 않는다** — 추론값이 섞이면 안전한 제품이
잘못 배제되고, 보호자가 그 값을 사실로 믿는다.

**`neutered`는 저장하되 급여 로직에 쓰지 않는다** (2026-08-13 팀 협의).
중성화가 기초대사량을 낮추는 건 사실이나 개체차가 커서 0/1로 정도를 표현할 수 없고,
'살이 찌기 쉽다'는 결과는 `body_type`이 더 직접적으로 담는다.

**급여목적은 제품 쪽에만 정형으로 둔다.** 보호자의 목적은 프로필 속성이 아니라 요청 속성이라
(이번 달은 다이어트, 다음 달은 피부) 프로필에 박으면 계속 낡는다. 요청 자연어에서 뽑는다.

---

## 3. 알러지 안전 판정

이 서비스에서 **틀리면 건강 사고가 되는 유일한 판정**이라 별도로 다룬다.

### 원칙 1 — SQL이 판정한다

LLM은 확률적으로 실패하지만 `NOT EXISTS`는 반드시 배제한다.
알러지 배제를 프롬프트에 맡기지 않는다.

원료명 문자열 비교로는 잡히지 않는다는 점이 핵심이다. `'닭가슴살'`, `'계육분'`, `'치킨오일'`은
서로 하나도 안 닮았지만 `ingredients.allergen_id`가 같은 알러지원을 가리키므로 조인으로 잡힌다.

### 원칙 2 — 모르는 것을 안전으로 처리하지 않는다

`NOT EXISTS`만 쓰면 "알러지원이 없다"와 "확인한 적이 없다"가 구분되지 않는다.
**데이터가 부실할수록 더 안전해 보이는** 실패가 생긴다.

그래서 판정을 2분법이 아니라 3분법으로 둔다 (`v_product_safety`):

| 판정 | 조건 |
|---|---|
| 위험 | 알러지원이 확인됨 → 후보에서 완전 제외 (감점이 아니다) |
| 판정불가 | 원료를 확인한 적이 없음 (`ingredients_verified = 0`) |
| 안전 | 원료 확인 완료 + 알러지원 없음 |

`products.ingredients_verified`는 기본값이 0이라 **신규 제품은 자동으로 판정불가에서 시작**하고,
원료표를 확인한 사람만 1로 올린다.

> **[미해결]** 같은 문제가 한 계층 아래 남아 있다. `ingredients.allergen_id IS NULL`이
> "검토 후 알러지원 아님"과 "미검토"를 구분하지 못해, 매핑이 비어 있으면 여전히 '안전'으로 통과한다.
> `ingredients.allergen_reviewed` 플래그가 필요하다. 상세는 `local/ToDo.md` §8.

---

## 4. 뷰

| 뷰 | 용도 |
|---|---|
| `v_pet_context` | 반려견 1행 요약. `birth_date`에서 나이를 계산하고 알러지를 묶어 LLM 프롬프트에 그대로 넣는다 |
| `v_review_docs` | 임베딩 문서 조립. 후기 본문 앞에 제품 분류·프로필 컨텍스트를 붙인다. `is_holdout = 1`은 제외 |
| `v_product_safety` | 반려견 × 제품 알러지 판정 3분법 |
| `v_safe_products` | 그중 `'안전'`만. 판정 로직이 `v_product_safety` 한 곳에만 있어 정책 변경 시 이 뷰만 고친다 |

---

## 5. 단계

- **1단계 (현재)** — 위 14 테이블. 추천이 돌아가는 최소 집합.
- **2단계** — `review_signals`(후기에서 뽑은 기호성·배변·알러지반응 수치),
  `recommendations` + `recommendation_evidence`(추천 근거 로그, GOAL 3부-2),
  `product_embeddings`(콜드스타트). 후기가 쌓인 뒤 착수.
- **3단계** — `subscriptions`/`payments`(GOAL 수익 구조), `places`(명소 추천, stretch goal).

### `review_signals`가 2단계인 이유

벡터 검색은 **질문과 비슷한 후기**를 뽑지 **대표성 있는 후기**를 뽑지 않는다.
후기 60개 중 50개가 "잘 먹어요"인 제품이라도, *"사료를 남겨요"* 라는 질문에는
의미가 가까운 "안 먹어요" 10개가 우선 검색된다. 그걸 받은 LLM은 기호성이 나쁘다고 오판한다.

각 후기를 미리 숫자로 바꿔두면 `GROUP BY`로 60개 전수 평균이 나온다.
**벡터 검색은 유사 사례 찾기, SQL 집계는 전수 통계** — 대체재가 아니라 역할이 다르다.
다만 후기가 쌓이기 전엔 집계할 게 없어 1단계에서는 벡터 검색만으로 충분하다.

---

## 6. 이관 계획

- **지금**: SQLite + BLOB 벡터 + numpy 완전탐색. 후기 1,439건이면 코사인 전량 계산이 수 ms라 인덱스 불필요.
- **배포 시**: PostgreSQL + pgvector. 관계형과 벡터를 한 DB에서 처리해 별도 벡터 DB 운영을 피한다.
  전용 벡터 DB는 이 규모에서 과하다.

`INTEGER PRIMARY KEY`는 `BIGINT GENERATED ALWAYS AS IDENTITY`로, `TEXT` 날짜는 `DATE`/`TIMESTAMPTZ`로,
`BLOB` 벡터는 `vector(384)`로 대응된다.
