# purchase_schema.md — 구매와 후기

어떤 아이가 무엇을 샀고, 그래서 어땠는지. **C블록 초안이다.**

| 테이블 | 설명 |
|---|---|
| [`purchases`](#purchases) | 구매 이력. 반려동물 1마리 : 구매 N건 |
| [`reviews`](#reviews) | 후기. 구매 1건 : 후기 최대 1건 |

반려동물은 [pet_schema.md](pet_schema.md), 제품은 [product_schema.md](product_schema.md).
리뷰 임베딩(D블록 `review_embeddings`)과 뷰 2개(`v_pet_context`, `v_review_docs`)는 아직 없다.

> 전체 색인은 [README.md](README.md).
> 이 문서와 `src/create_schema/` 가 어긋나면 **코드가 맞다.**

---

## purchases

구매 이력. 추천 근거(재구매·기호성)와 후기의 뿌리다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `purchase_id` | INTEGER | PK | 대리키 |
| `pet_id` | INTEGER | NOT NULL, FK → [`pets`](pet_schema.md#pets), ON DELETE **RESTRICT** | **누구를 위해 샀는지** |
| `product_id` | INTEGER | NOT NULL, FK → [`products`](product_schema.md#products), ON DELETE RESTRICT | 산 제품 |
| `quantity` | INTEGER | NOT NULL, DEFAULT 1, > 0 | 수량 |
| `unit_price_krw` | INTEGER | NOT NULL, >= 0 | **구매 시점의** 개당 가격(원) |
| `age_month_at_purchase` | INTEGER | >= 0, **NULL 허용** | **구매 시점의** 개월 나이. NULL = `birth_date` 미입력 |
| `size_at_purchase` | INTEGER | `1~5`, **NULL 허용** | **구매 시점의** 체구. NULL = 그때 미입력 |
| `purchased_at` | TEXT | NOT NULL, ISO-8601 | 구매 시각 |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| `idx_purchases_pet` | (`pet_id`, `purchased_at`) | "이 아이의 최근 구매" — 재구매 판정, 프로필 문맥 |
| `idx_purchases_product` | (`product_id`, `purchased_at`) | "이 제품을 산 사람들" — 제품별 후기 목록의 진입점 |

### 설계 노트

#### `unit_price_krw` — 그때 가격을 적는다

`products.price_krw` 는 **현재가**라 시간이 지나면 변한다. 조인해서 쓰면 작년 구매의 총액이
오늘 가격으로 바뀐다. **그때 얼마였는지는 사실이지 파생값이 아니다.**

#### `age_month_at_purchase` — 앱이 계산해서 넣는다

SQL 로 내려면 `julianday` 차이를 `30.44`(평균 일수)로 나눠야 하는데 근사라
**생일 근처에서 틀린다** — 2023-03-15 생 아이의 만 4년 나이가 47개월로 나온다.
[`petcalc.age_months()`](../../src/petcalc.py) 가 달력으로 센다.

조회할 때마다 계산하지 않는다. 저장해두면 행마다 시점이 다른 집계에서도 SQL 은 컬럼을 읽기만 한다.

```python
from petcalc import age_months          # 애완동물 나이 계산
con.execute("INSERT INTO purchases(..., age_month_at_purchase) VALUES (..., ?)",
            (..., age_months(pet_birth_date, purchased_at)))
```

필터는 여전히 SQL 이 한다 — 계산만 앱으로 온 것이다:
`WHERE ?1 BETWEEN pr.target_age_min_month AND pr.target_age_max_month`

**대가**: `birth_date` 를 나중에 입력받으면 이미 쌓인 행이 NULL 로 남는다.
**`pets.birth_date` 를 UPDATE 할 때 같은 트랜잭션에서 그 아이의 기존 구매를 백필해야 한다.**

#### `size_at_purchase` — `pets.size` 와 둘 다 있다

`unit_price_krw` 와 같은 구조다. 다른 질문에 답한다.

| | 답하는 질문 | 쓰임 |
|---|---|---|
| `size_at_purchase` | 그때 어땠나 | 후기 해석, 세그먼트 집계 |
| [`pets.size`](pet_schema.md#pets) | 지금 어떤가 | 추천 필터 (`target_size_min`/`max`) |

**나이와 다르다.** 나이는 `birth_date` 로 다시 계산되지만 `pets.size` 는 UPDATE 로 덮어써져
**원본이 사라진다.** 여기 없으면 복원할 방법이 없다.

기본 가정은 "자랐다"라서 과거 행은 그대로 둔다. 초보 견주가 잘못 본 값을 고친 **정정**이면
소급돼야 하므로 앱이 과거 행도 같이 고친다 ([`../docu.md`](../docu.md) §1). DB 는 둘을 구별 못 한다.

#### 삭제는 위아래 모두 RESTRICT

구매 이력이 있으면 제품도 반려동물도 지울 수 없다.
단종은 `products.is_active = 0`, 반려동물은 `pets.inactive_at` 이다.

`pet_id` 는 원래 CASCADE 였다. 그러면 계정 파기 한 줄이
`users` → `pets` → `purchases` → `reviews` 4단을 타고 **후기까지 지운다.**
`reviews.purchase_id` 만 CASCADE 로 남겼다 — 구매 오등록을 정정하면 그 후기는 근거를 잃는다.

#### 두지 않는 컬럼

| | 왜 | 대신 |
|---|---|---|
| `user_id` | **애완동물** 정보로 추천하는 시스템이다. 아이를 다른 계정으로 옮길 때 두 곳을 맞춰야 한다 | `pets.user_id` 조인 |
| 총액 | 고칠 값이 하나 더 생긴다 | `quantity * unit_price_krw` |
| 재구매 플래그 | 두 번째 구매 때 첫 행을 UPDATE 해야 하고, 한 건이 사라지면 플래그가 남는다 | 아래 쿼리 |
| `created_at` / `updated_at` | append-only 라 `purchased_at` 과 같은 값이 된다. 둘이 나란히 있으면 **적재 순서**로 정렬하는 사고가 난다 | `purchased_at` |
| 환불 | 결제자가 아니라 추천자라 환불 이벤트가 들어올 경로가 없다 | 다루게 되면 `refunded_at TEXT` (플래그 아님, 규칙 3) |

```sql
-- 재구매: 같은 (pet_id, product_id) 가 2건 이상
SELECT product_id, count(*) AS times
  FROM purchases
 WHERE pet_id = ?1
 GROUP BY product_id
HAVING count(*) > 1
```

`idx_purchases_pet` 이 이 집계를 그대로 커버한다.
`refunded_at` 을 넣게 되면 **모든 집계에 `AND refunded_at IS NULL` 이 붙어야 한다.**

---

## reviews

후기. 임베딩 대상 텍스트가 여기 있다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `purchase_id` | INTEGER | **PK**, FK → [`purchases`](#purchases), ON DELETE CASCADE | 어느 구매에 대한 후기인지 |
| `rating` | INTEGER | NOT NULL, 1~5 | 별점 |
| `body` | TEXT | NOT NULL, 공백만은 거부 | 후기 본문. **임베딩 대상** |
| `is_holdout` | INTEGER | NOT NULL, DEFAULT 0, 0/1 | 1 = 추천 정확도 평가용으로 떼어둔 행. **임베딩 색인에서 제외** |
| `reviewed_at` | TEXT | NOT NULL, ISO-8601 | 작성 시각 |

### 설계 노트

#### `purchase_id` 를 PK 로 쓴다 (`review_id` 대리키 없음)

구매 1건에 후기 1건이라 별도 번호는 아무도 참조하지 않는다. PK 로 잡으면
**"같은 구매에 후기 두 번"이 그냥 막힌다** — 대리키를 두면 UNIQUE 인덱스를 따로 챙겨야 하고,
빠뜨리면 중복이 조용히 들어간다. `product_nutrition` 이 `product_id` 를 PK 로 쓰는 것과 같다.

**구매 없는 후기는 받지 않는다.** "지어내지 않고 실제 후기에서 찾아온다"가 서비스의 근거라
FK 가 그 전제를 강제한다. 체험단·미구매 후기를 받게 되면 PK 를 대리키로 바꾸고
`purchase_id` 를 NULL 허용 FK 로 내린다 — 초안 단계에서 되돌리기 가장 쉬운 결정이라 좁게 잡는다.

#### `is_holdout` — 구매가 아니라 후기에 붙는다

떼어놓는 대상이 "평가용 정답 텍스트"이기 때문이다. 구매 이력 자체는 프로필 문맥으로 계속 쓴다.

#### 두지 않는 컬럼

| | 왜 | 대신 |
|---|---|---|
| `allergy_reaction` | **층이 틀렸다.** "먹고 반응이 났다"는 결국 이 아이에게 알러지가 있다는 사실이라 [`pet_allergies`](pet_schema.md#pet_allergies) 자리다. 거기 들어가야 [`safe_products.py`](../../src/safe_products.py) 가 다음부터 **배제**한다 — 후기에 0/1 로 적으면 기록만 남고 아무도 보호받지 못한다. 원료가 여럿이면 원인 지목도 못 한다 | `body` 에서 읽는다. [`../GOAL.md`](../GOAL.md) 가 "리뷰 텍스트 속에서 알레르기 반응을 읽어내어"를 D블록 임베딩의 일로 정해뒀다 |
| `created_at` / `updated_at` | 수정·삭제 기능이 없어 `rating`/`body` 가 불변이다. `created_at` 은 `reviewed_at` 과 같은 값이 된다. 유일한 UPDATE 인 `is_holdout` 은 운영 작업이라 시각을 읽을 사람이 없다 | `reviewed_at` |

**NULL 허용 컬럼이 없다.** 다섯 컬럼 전부 NOT NULL — 후기가 있다는 것 자체가
"보호자가 별점과 본문을 남겼다"는 뜻이라 빠질 값이 없다.

#### 인덱스 없음

후기 조회는 항상 제품이나 반려동물에서 출발해 `purchases` 를 거치므로
`idx_purchases_product` / `idx_purchases_pet` 이 이미 진입점을 덮는다.
`is_holdout` 단독 인덱스는 값이 두 가지뿐이라 옵티마이저가 어차피 안 탄다.

### 남은 것

- `review_embeddings` (D블록) — `purchase_id` 를 FK 로 받고 벡터는 BLOB
- `v_review_docs` — 임베딩에 넣을 문서 조립(후기 본문 + 작성자 아이의 프로필). `is_holdout = 0` 만
- `v_pet_context` — 아이 한 마리의 프로필 + 구매 이력 요약

**아직 검증되지 않은 것** — 이 초안은 스키마 생성과 제약 차단만 확인했다.
실제 더미 데이터 적재와 임베딩 파이프라인은 아직 안 돌렸다.
