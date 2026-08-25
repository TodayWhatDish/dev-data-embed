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
| `purchased_at` | TEXT | NOT NULL, ISO-8601 | 구매 시각 |
| `quantity` | INTEGER | NOT NULL, DEFAULT 1, > 0 | 수량 |
| `unit_price_krw` | INTEGER | NOT NULL, >= 0 | **구매 시점의** 개당 가격(원) |
| `weight_kg_at_purchase` | REAL | > 0, **NULL 허용** | **구매 시점의** 체중. NULL = 그때 미입력 |
| `age_month_at_purchase` | INTEGER | >= 0, **NULL 허용** | **구매 시점의** 개월 나이. NULL = `birth_date` 미입력 |
| `created_at` | TEXT | NOT NULL, DEFAULT now | 행 생성 시각 |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| `idx_purchases_pet` | (`pet_id`, `purchased_at`) | "이 아이의 최근 구매" — 재구매 판정, 프로필 문맥 |
| `idx_purchases_product` | (`product_id`, `purchased_at`) | "이 제품을 산 사람들" — 제품별 후기 목록의 진입점 |

### 설계 노트

**`user_id` 를 두지 않는다.** 보호자는 `pets.user_id` 를 조인하면 나온다. 구매 행에 다시 적으면
아이를 다른 계정으로 옮길 때 두 곳을 맞춰야 하고, 빠뜨리면 조용히 어긋난다.
"보호자가 아이를 지정하지 않고 구매"는 이 서비스에 없다 — 추천 단위가 개체이기 때문이다.

**`unit_price_krw` 를 저장한다. `products.price_krw` 를 조인하지 않는다.**
`products.price_krw` 는 **현재가**라서 시간이 지나면 변한다. 조인해서 쓰면 작년 구매의 총액이
오늘 가격으로 바뀐다. 규칙 3(사실을 저장하고 상태는 파생)의 반대 방향처럼 보이지만 같은 원칙이다 —
**그때 얼마였는지는 사실이지 파생값이 아니다.**

**총액 컬럼을 두지 않는다.** `quantity * unit_price_krw` 로 나온다. 저장하면 둘을 고칠 때마다
같이 고쳐야 하는 세 번째 값이 생긴다.

**재구매 여부를 컬럼으로 두지 않는다.** 같은 `(pet_id, product_id)` 구매가 2건 이상이면 재구매다.

```sql
SELECT product_id, count(*) AS times
  FROM purchases
 WHERE pet_id = ?1
 GROUP BY product_id
HAVING count(*) > 1
```

플래그로 두면 두 번째 구매를 넣을 때 첫 번째 행을 UPDATE 해야 하고, 환불로 한 건이 사라지면
플래그가 남는다. `idx_purchases_pet` 이 이 집계를 그대로 커버한다.

**체중·나이 스냅샷을 저장한다. `pets` 를 조인하지 않는다 (2026-08-24).**
바로 위 `unit_price_krw` 와 **같은 원칙이다** — 그때 몇 kg 이었는지는 사실이지 파생값이 아니다.
`pets.weight_kg` / `birth_date` 를 조인해서 쓰면 **지금**의 값이 나오고, 강아지는 자란다.
3년 전 소형견 시절에 쓴 후기가 오늘 대형견 후기로 해석되어 세그먼트 추천이 조용히 틀려진다.

나이를 `age_month` 로 박는 것은 [`pets.birth_date`](pet_schema.md#pets) 에서 파생하라는
규칙 3의 예외처럼 보이지만 아니다. 파생의 기준점이 "지금"이 아니라 "구매 시점"인데,
그 시점은 이 행에만 있다. 계산은 앱이 INSERT 때 한 번 한다:

```sql
INSERT INTO purchases(..., weight_kg_at_purchase, age_month_at_purchase)
SELECT ..., p.weight_kg,
       CAST((julianday(:purchased_at) - julianday(p.birth_date)) / 30.44 AS INTEGER)
  FROM pets p WHERE p.pet_id = :pet_id
```

`size` 는 안 넣는다. `weight_kg` 에서 나오고, 척도가 바뀌면 다시 계산할 수 있어야 한다.
체구 구간은 앱의 판단이지 사실이 아니다.

**삭제는 위아래 모두 RESTRICT 다 (2026-08-24).** 구매 이력이 있으면 제품도 반려동물도 지울 수 없다.
단종은 `products.is_active = 0`, 반려동물은 `pets.inactive_at` 으로 비활성 처리한다.

`pet_id` 는 원래 CASCADE 였다. 그러면 계정 파기 한 줄이
`users` → `pets` → `purchases` → `reviews` 4단을 타고 **후기까지 지운다.**
후기는 이 저장소의 핵심 자산이라 그 경로를 DB 가 막는다. 파기는 삭제가 아니라
익명화 UPDATE 다 ([`../docu.md`](../docu.md) §1).

`reviews.purchase_id` 만 CASCADE 로 남겼다. 구매 오등록을 정정하면 그 후기는 근거를 잃으므로
같이 사라지는 게 맞다. 구매 자체가 RESTRICT 로 보호되니 이 경로가 열리는 건
운영자가 의도적으로 구매 행을 지울 때뿐이다.

---

## reviews

후기. 임베딩 대상 텍스트가 여기 있다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `purchase_id` | INTEGER | **PK**, FK → [`purchases`](#purchases), ON DELETE CASCADE | 어느 구매에 대한 후기인지 |
| `rating` | INTEGER | NOT NULL, 1~5 | 별점 |
| `body` | TEXT | NOT NULL, 공백만은 거부 | 후기 본문. **임베딩 대상** |
| `allergy_reaction` | INTEGER | 0/1, **NULL 허용** | 알러지 반응 여부. NULL = 후기에 언급 없음 |
| `is_holdout` | INTEGER | NOT NULL, DEFAULT 0, 0/1 | 1 = 추천 정확도 평가용으로 떼어둔 행. **임베딩 색인에서 제외** |
| `reviewed_at` | TEXT | NOT NULL, ISO-8601 | 작성 시각 |
| `created_at` / `updated_at` | TEXT | NOT NULL, DEFAULT now | 행 생성/수정 시각 |

**인덱스 없음.** 후기 조회는 항상 제품이나 반려동물에서 출발해 `purchases` 를 거치므로
`idx_purchases_product` / `idx_purchases_pet` 이 이미 진입점을 덮는다. `is_holdout` 단독 인덱스는
값이 두 가지뿐이라 옵티마이저가 어차피 안 탄다.

### 설계 노트

**`review_id` 를 따로 두지 않고 `purchase_id` 를 PK 로 쓴다.** 구매 1건에 후기 1건이므로
별도 번호는 아무도 참조하지 않는다. PK 로 잡아두면 **"같은 구매에 후기 두 번"이 그냥 막힌다** —
번호를 PK 로 두면 이걸 막는 UNIQUE 인덱스를 따로 챙겨야 하고, 빠뜨리면 중복이 조용히 들어간다.
`product_nutrition` 이 `product_id` 를 PK 로 쓰는 것과 같은 패턴이다.

**구매 없는 후기는 받지 않는다.** FK 가 이걸 강제한다. "지어내지 않고 실제 후기에서 찾아온다"가
서비스의 근거인데, 구매와 끊어진 후기를 허용하면 그 문장이 성립하지 않는다.
체험단·미구매 후기를 받게 되면 이 PK 를 `review_id` 대리키로 바꾸고 `purchase_id` 를 NULL 허용
FK 로 내려야 한다 — **초안 단계에서 되돌리기 가장 쉬운 결정이므로 지금은 좁게 잡는다.**

**`allergy_reaction` 만 NULL 을 허용한다.** 0(반응 없었음)과 NULL(후기에 언급 없음)은 다르다.
둘을 0 으로 뭉개면 "언급이 없다"가 "괜찮았다"로 읽히고, 이건 도메인 규칙 2
(모르는 것을 안전으로 처리하지 않는다)를 정면으로 어긴다.
다만 **이 값은 추천의 하드 필터가 아니다.** 알러지 배제는 `v_product_safety` 한 군데서만 한다 —
후기의 자기 보고를 배제 근거로 쓰면 판정 로직이 두 군데가 된다. 여기 값은 근거 문장을 고를 때
쓰는 신호이지 필터가 아니다.

**`is_holdout` 은 후기에 붙지 구매에 붙지 않는다.** 떼어놓는 대상이 "평가용 정답 텍스트"이기
때문이다. 구매 이력 자체는 프로필 문맥으로 계속 쓴다.

### 남은 것

- `review_embeddings` (D블록) — `purchase_id` 를 FK 로 받고 벡터는 BLOB
- `v_review_docs` — 임베딩에 넣을 문서 조립(후기 본문 + 작성자 아이의 프로필). `is_holdout = 0` 만
- `v_pet_context` — 아이 한 마리의 프로필 + 구매 이력 요약

**아직 검증되지 않은 것** — 이 초안은 스키마 생성과 제약 차단만 확인했다.
실제 더미 데이터 적재와 임베딩 파이프라인은 아직 안 돌렸다.
