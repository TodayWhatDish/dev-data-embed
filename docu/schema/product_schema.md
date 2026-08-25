# product_schema.md — 제품

판매 제품과 그 속성, 그리고 알러지 판정 뷰.

| 테이블 | 설명 |
|---|---|
| [`product_categories`](#product_categories) | 제품 분류 코드표 (읽기 전용) |
| [`feeding_purposes`](#feeding_purposes) | 급여목적 코드표 (읽기 전용) |
| [`products`](#products) | 판매 제품. 추천 후보 집합의 원본 |
| [`product_animal_categories`](#product_animal_categories) | 제품 ↔ 대상 축종 (다대다) |
| [`product_nutrition`](#product_nutrition) | 영양성분 (1:1) |
| [`product_feeding_purposes`](#product_feeding_purposes) | 제품 ↔ 급여목적 (다대다) |
| [`ingredients`](#ingredients) | 원료 마스터. **알러지 판정의 연결 고리** |
| [`ingredient_allergens`](#ingredient_allergens) | 원료 ↔ 알러지원 (다대다) |
| [`product_ingredients`](#product_ingredients) | 제품 ↔ 원료 (다대다) |

| 뷰 | 설명 |
|---|---|
| [`v_product_safety`](#v_product_safety) | 반려동물 × 제품 알러지 판정 (3분법) |
| [`v_safe_products`](#v_safe_products) | 추천 후보군 |

축종(`animal_categories`)과 알러지원(`allergens`)은 반려동물 도메인과 공유하므로
[common_schema.md](common_schema.md) 에 있다.

> 전체 색인은 [README.md](README.md).
> 이 문서와 `src/create_schema/` 가 어긋나면 **코드가 맞다.**

---

## product_categories

제품 분류 코드표. 대분류(사료/간식)와 소분류(덴탈껌/트릿…)를 `parent_id` 한 컬럼으로 한 테이블에
담는다. **앱 기준 읽기 전용** — 대분류는 시드, 소분류는 관리자가 채운다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `product_category_id` | INTEGER | PK | 대리키 |
| `parent_id` | INTEGER | FK → `product_categories` (RESTRICT) | 상위 분류. NULL = 대분류 |
| `name_ko` | TEXT | NOT NULL, UNIQUE | 분류명(한글) |
| `name_eng` | TEXT | UNIQUE | 분류명(영문) |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| `idx_product_categories_parent` | (`parent_id`) | "이 대분류의 소분류 전부" |

**초기 데이터** — `SEEDS` 가 넣는다. `products.product_category_id` 가 NOT NULL 이라 이 표가 비어 있으면
제품을 하나도 넣을 수 없다.

| `product_category_id` | `parent_id` | `name_ko` |
|---|---|---|
| `1` | | 사료 |
| `2` | | 간식 |
| `3` | `2` | 덴탈껌 |
| `4` | `2` | 트릿 |
| `5` | `2` | 수제간식 |

### 설계 노트

**`CHECK (category IN ('사료','간식'))` 대신 테이블로 둔 이유는
[`animal_categories`](common_schema.md#animal_categories) 와 같다** — SQLite 는 CHECK 를 바꾸려면
테이블을 재생성해야 하지만 코드표는 행 하나 INSERT 로 끝난다.
`GOAL.md` 의 타겟이 "반려동물 사료, 간식"이라 영양제·용품이 늘어날 여지가 실제로 있다.

**대분류/소분류를 두 컬럼(`category` + `sub_category`)으로 쪼개지 않는다.** 두 컬럼이면 소분류를
추가할 때마다 어느 대분류에 속하는지가 데이터가 아니라 관행으로만 남는다.
[`allergens`](common_schema.md#allergens) 와 같은 `parent_id` 형태라 계층이 DB 안에 남고,
앱은 이미 `allergens` 트리를 다루는 코드를 갖고 있다.

**사료의 소분류를 시드하지 않는다.** 옛 CSV 의 `'건식사료'`·`'퍼피사료'` 같은 값은
`products.food_form` 과 `target_age_min_month`/`max_month` 가 이미 담고 있다. 여기에 또 만들면
같은 사실이 두 군데에 앉아 서로 어긋난다. 소분류가 실제로 정보를 더하는 쪽은 간식이다
(덴탈껌은 형태도 목적도 다르다).

**계층 깊이가 균일하지 않아도 된다.** 사료는 소분류가 0개고 간식은 3개다. 트리는 원래 그래도 된다.

---

## feeding_purposes

급여목적 코드표(관절/다이어트/피부…). **앱 기준 읽기 전용** — 시드로 채운다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `feeding_purpose_id` | INTEGER | PK | 대리키 |
| `name_ko` | TEXT | NOT NULL, UNIQUE | 목적명(한글) |
| `name_eng` | TEXT | UNIQUE | 목적명(영문). 앱 분기·i18n 용 |

**초기 데이터** — 관절 / 다이어트 / 피부 / 치아 / 신장 / 소화.

### 설계 노트

**급여목적을 [`pets`](pet_schema.md#pets) 쪽에 두지 않는다.** 목적은 프로필 속성이 아니라
**요청 속성**이다 — 이번 달은 다이어트, 다음 달은 피부. 프로필에 박으면 계속 낡는다.
이건 `pets` 가 급여 형태·식성을 저장하지 않는 것과 같은 판단이다.
보호자의 목적은 요청 자연어에서 뽑고, **제품 쪽만 정형으로 관리한다.**

---

## products

판매 제품(사료/간식). 추천 후보 집합의 원본.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `product_id` | INTEGER | PK | 대리키 |
| `product_category_id` | INTEGER | NOT NULL, FK → [`product_categories`](#product_categories) (RESTRICT) | 제품 분류 |
| `brand` | TEXT | NOT NULL | 브랜드명 |
| `name` | TEXT | NOT NULL | 제품명 |
| `food_form` | TEXT | CHECK `건식`/`습식`/`동결건조`/`생식`/`공용` | 급여 형태 |
| `price_krw` | INTEGER | NOT NULL, CHECK `>= 0` | 판매가(원) |
| `weight_g` | INTEGER | NOT NULL, CHECK `> 0` | 내용량(g) |
| `kcal_per_100g` | INTEGER | CHECK `> 0` | 100g당 열량. 급여량 계산 |
| `target_size_min` | INTEGER | NOT NULL, DEFAULT `1`, CHECK `1~5` | 대상 체구 하한. [`pets.size`](pet_schema.md#pets) 와 **같은 코드** |
| `target_size_max` | INTEGER | NOT NULL, DEFAULT `5`, CHECK `1~5` | 대상 체구 상한 |
| `target_age_min_month` | INTEGER | NOT NULL, DEFAULT `0`, CHECK `>= 0` | 대상 월령 하한 |
| `target_age_max_month` | INTEGER | NOT NULL, DEFAULT `1200`, CHECK `>= 0` | 대상 월령 상한 |
| `description` | TEXT | | 제품 설명. 후기 없는 신규 제품(콜드스타트)의 임베딩 대상 |
| `ingredients_verified` | INTEGER | NOT NULL, DEFAULT `0`, CHECK `0`/`1` | 원료표를 사람이 확인해 등록했는가 |
| `is_active` | INTEGER | NOT NULL, DEFAULT `1`, CHECK `0`/`1` | 판매중 여부 |
| `created_at` | TEXT | NOT NULL, DEFAULT `datetime('now')` | 등록 시각 |
| `updated_at` | TEXT | NOT NULL, DEFAULT `datetime('now')` | 마지막 수정 시각 |

**테이블 제약** — `CHECK (target_size_min <= target_size_max)`, `CHECK (target_age_min_month <= target_age_max_month)`

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| `idx_products_filter` | (`product_category_id`, `is_active`) | 후보군 1차 필터 + **카테고리 단독 제품 조회**. 선두가 FK 라 부모행 삭제 검사도 겸한다 |

`product_category_id` 단독 인덱스는 두지 않는다. 뒤 컬럼이라 단독 조회는 SEARCH 가 아니라 커버링
인덱스 SCAN 이지만, 부모([`product_categories`](#product_categories))가 시드 5행이라 삭제 검사가
거의 돌지 않고 실제 필터는 항상 `is_active` 와 함께 온다.

**연결 테이블로 참조하는 것** — 제품 하나가 여러 개를 가질 수 있어 컬럼으로 담기지 않는다.

| 항목 | 테이블 |
|---|---|
| 대상 축종 | [`product_animal_categories`](#product_animal_categories) |
| 급여목적 | [`product_feeding_purposes`](#product_feeding_purposes) |
| 원료 | [`product_ingredients`](#product_ingredients) |

### 설계 노트

**대상 범위를 `'전체'` 라는 마법값이 아니라 범위의 양 끝으로 표현한다.**
[`pets.size`](pet_schema.md#pets) 가 정수 1~5 가 되면서 옛 초안의
`target_size TEXT CHECK IN ('소형','중형','대형','전체')` 는 쓸 수 없게 됐다.
대신 하한/상한 두 컬럼을 둔다.

| 표현하려는 것 | `target_size_min` | `target_size_max` |
|---|---|---|
| 소형견 전용 | `2` | `2` |
| 소형~중형 | `2` | `3` |
| 전 체구 | `1` | `5` (기본값) |

`'소형~중형'` 같은 실제 표기가 그대로 담기고, 필터가 `BETWEEN` 하나로 끝난다:

```sql
WHERE :pet_size BETWEEN target_size_min AND target_size_max
```

**연령도 같은 방식이되 단위가 월령이다.** `'퍼피'/'성견'/'시니어'` 를 코드로 두지 않는 이유는
두 가지다. (1) `pets` 는 나이를 저장하지 않고 `birth_date` 에서 계산하므로 나오는 값이 연속값이다.
(2) **시니어 기준이 축종·체구마다 다르다** — 대형견은 6세, 소형견은 9세, 고양이는 11세쯤부터다.
등급으로 굳히면 그 차이를 담을 곳이 없다. `1200` 개월(100년)은 '상한 없음'을 뜻한다.

**대상 축종은 컬럼이 아니라 [`product_animal_categories`](#product_animal_categories) 다.**
이유는 그 항목에 적었다.

**`product_category_id` 는 단일 FK 다 — 제품 하나에 분류 하나. `사료 겸 간식`은 두지 않는다.**
2026-08-17 결정: **간식이면 간식, 사료면 사료로 무조건 하나를 고른다.** 등록하는 사람이 판단한다.

**대분류(사료/간식) 판정은 한 칸만 올라가면 된다.** 제품은 대분류(`사료`)를 직접 가리킬 수도,
소분류(`덴탈껌`)를 가리킬 수도 있다. 계층이 **2단계로 고정**이므로 재귀가 필요 없다:

```sql
-- 이 제품의 대분류 id
SELECT COALESCE(c.parent_id, c.product_category_id)
  FROM products p
  JOIN product_categories c ON c.product_category_id = p.product_category_id
 WHERE p.product_id = ?
```

**2단계 고정은 DB 가 강제하지 않는다** — `product_categories` 에 3단계를 넣으면 위 식이 조용히
틀린 답을 낸다(손자가 자기 부모를 대분류로 보고한다). 소분류의 소분류를 만들지 않는 것은
운영 규칙이며 [`../docu.md`](../docu.md) 소관이다.

**브랜드를 테이블로 분리하지 않는다.** 자체 판매 B2C 구조라 브랜드별 정산/제휴 관리가 없다.
필요해지면 그때 `brands` 로 분리한다.

**`is_active` 로 내리지, 행을 지우지 않는다.** 단종 제품을 삭제하면 과거 구매/후기가 끊긴다.
[`pets.inactive_at`](pet_schema.md#pets) 과 같은 판단이다.

**`idx_products_filter` 는 `product_category_id` 가 선두다 — 순서가 실제로 이득을 만든다.**
추천 경로를 타지 않고 **제품만으로 거르는 조회**가 따로 있기 때문이다:

```sql
SELECT ... FROM products WHERE product_category_id = ?   -- "간식 목록"
```

`is_active` 를 선두에 두면 이 조회가 **풀스캔**이 된다. `is_active` 는 값이 `0`/`1` 뿐이라
`ANALYZE` 를 돌린 뒤에는 skip-scan 이 붙지만, `execute_schema.py` 는 `ANALYZE` 를 돌리지 않으므로
갓 만든 `user.db` 에는 통계가 없어 실제로 풀스캔한다(측정 확인).

| 조회 | `(is_active, cat)` | `(cat, is_active)` |
|---|---|---|
| `cat = ?` 단독 | 풀스캔 (ANALYZE 후 skip-scan) | **SEARCH** |
| `is_active = 1 AND cat = ?` | SEARCH | SEARCH (동일) |
| `is_active = 1` 단독 | SEARCH | skip-scan |

두 컬럼 모두 등호로 오는 후보군 필터는 순서와 무관하게 같다. 잃는 것은 `is_active` 단독 조회뿐인데,
그건 활성 제품 **전부**를 뽑는 것이라 애초에 인덱스가 의미 없다.
덤으로 선두가 FK 라 `product_categories` 부모행 삭제 검사도 이 인덱스가 겸한다 —
FK 단독 인덱스를 따로 만들 이유가 사라졌다.

### 이 테이블은 식품 전용이다 — 장난감·용품을 넣을 때 할 일

지금 `products` 에는 **식품에만 뜻이 있는 컬럼**이 섞여 있다.

| 컬럼 | 장난감에 넣으면 |
|---|---|
| `food_form` | 무의미 (NULL 이면 그만) |
| `kcal_per_100g` | 무의미 (NULL 이면 그만) |
| `weight_g` | **NOT NULL** 이라 반드시 값을 넣어야 한다 |
| `target_age_*` | 뜻이 남는다 (퍼피용 치발기) |
| `target_size_*` | 뜻이 남는다 (소형견용 장난감) |

즉 걸리는 건 `weight_g` 하나다. 나머지([`product_nutrition`](#product_nutrition),
[`product_ingredients`](#product_ingredients), [`product_feeding_purposes`](#product_feeding_purposes))는
**이미 별도 테이블**이라 행이 0개면 그만이라 아무것도 안 바꿔도 된다.

**그런데도 지금 나누지 않는다.** 이 레포에는 마이그레이션이 없기 때문이다 — 로더가 매 실행마다
`DROP` 후 전체 재구축하고 운영 데이터가 없으므로, 나중에 식품 컬럼을 `product_food` 1:1 테이블로
빼는 비용이 **스크립트 수정 + 재생성**이 전부다. 지금 미리 추상화하면 요구사항도 데이터도 없는
상태에서 검증되지 않은 구조를 만들게 된다.

나눌 때 옮길 것: `food_form`, `weight_g`, `kcal_per_100g` →
`product_food(product_id PK)`. `product_nutrition` 이 이미 그 패턴이다.
`target_size_*` / `target_age_*` 는 `products` 에 남는다 — 물품에도 뜻이 있다.

---

## product_animal_categories

제품 ↔ 대상 축종 (다대다). "이 제품을 어느 축종에게 줄 수 있는가."

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `product_id` | INTEGER | PK, FK → [`products`](#products) (CASCADE) | 제품 |
| `animal_category_id` | INTEGER | PK, FK → [`animal_categories`](common_schema.md#animal_categories) (RESTRICT) | 대상 축종 |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| (복합 PK) | (`product_id`, `animal_category_id`) | 중복 등록 차단 + "이 제품의 대상 축종들" |
| `idx_prod_ac_category` | (`animal_category_id`) | "이 축종에게 줄 수 있는 제품 전부" — 후보군 필터가 이 방향으로 탄다 |

### 지금 다루는 축종은 개와 고양이 둘뿐이다

**앵무새 같은 다른 축종은 넣지 않는다** — [`GOAL.md`](../GOAL.md) 의 '대상 축종'이
개·고양이로 확정되어 있다. 실제로 표현해야 하는 조합은 세 가지뿐이다.

| 실제 케이스 | 행 |
|---|---|
| 강아지 사료 | (제품, 개) |
| 고양이 사료 | (제품, 고양이) |
| 개·묘 공용 껌 | (제품, 개) + (제품, 고양이) |

**축종이 둘뿐인데도 연결 테이블인 이유는 '표현 불가' 때문이 아니다.** 축종이 정확히 둘이면
NULL 컬럼으로도 '둘 다'가 표현되긴 한다. 진짜 이유는 아래 두 가지이고, 둘 다 축종 수와 무관하다.

### 설계 노트

**`products.animal_category_id INTEGER NULL`(NULL = 전 축종 공용) 을 쓰다가 갈아탄 것이다.**

**① NULL 은 '공용'과 '미입력'을 구분하지 못한다 — 그리고 fail-open 이다.**
축종을 아직 안 정한 제품이 NULL 로 남으면 **모든 프로필에 노출된다.** 데이터가 부실할수록 더 넓게
노출되는, 방향이 반대인 실패다. 연결 테이블은 0행 = 아무에게도 안 뜸이라
`products.ingredients_verified` 가 미확인 제품을 '판정불가'로 떨어뜨리는 것과 같은 방향이다.

| | NULL 컬럼 | 연결 테이블 |
|---|---|---|
| 개 전용 | `1` | 1행 |
| 개+고양이 공용 | `NULL` | 2행 |
| **축종 미입력** | `NULL` — 공용과 구분 안 됨, 전원에게 노출 | **0행 — 아무에게도 안 뜸** |

**② 축종을 늘릴 때 기존 행의 의미가 바뀌지 않는다.**
NULL 컬럼에서는 축종을 하나 더 넣는 순간 기존 `NULL` 행 **전부**가 "새 축종에게도 준다"로
조용히 뜻이 바뀐다. 연결 테이블은 행이 명시적이라 아무것도 안 바뀐다.
이건 [`allergens` 가 평면 목록을 버린 이유](common_schema.md#검토했다-버린-안)와 같은 형태다 —
"전체를 골랐다"는 사실이 어디에도 안 남으면 나중에 추가된 항목을 판단할 수 없다.

그래서 **축종이 앞으로도 둘뿐이더라도 이 구조를 유지한다.** 셋째 축종이 정말 필요해지는 날에는
`animal_categories` 에 행 하나 INSERT + 해당 제품에 연결 행 추가로 끝난다.

**행 수가 곧 대상 범위다.** [`pet_breeds`](pet_schema.md#pet_breeds) 와 같은 읽는 법이다.

| 행 수 | 뜻 |
|---|---|
| 0 | 대상 축종 미등록 → **아무에게도 후보로 뜨지 않는다** |
| 1 | 단일 축종 전용 |
| 2 이상 | 공용 |

**0행이 fail-closed 인 것이 이 설계의 이점이다.** NULL 컬럼은 미입력이 곧 '전 축종 통과'라
방향이 반대였다 — 데이터가 부실할수록 더 넓게 노출됐다. `products.ingredients_verified` 가
미확인 제품을 '판정불가'로 떨어뜨리는 것과 같은 방향으로 맞췄다.

**필터가 오히려 단순해진다.** `(= ? OR IS NULL)` 은 인덱스를 반만 타지만, 조인은
`idx_prod_ac_category` 를 covering index 로 그대로 탄다.

```sql
JOIN product_animal_categories pac ON pac.animal_category_id = :pet_category
JOIN products pr ON pr.product_id = pac.product_id
```

**축종 정합성은 여기서 끝나지 않는다.** 이 테이블은 "제품이 어느 축종용인가"만 말한다.
[`pet_breeds`](pet_schema.md#pet_breeds) 의 축종 정합성(개에게 고양이 품종을 연결)은 여전히 앱이 막는다.

---

## product_nutrition

제품 영양성분(보장성분표). [`products`](#products) 와 **1:1** 이지만 테이블을 분리한다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `product_id` | INTEGER | PK, FK → [`products`](#products) (CASCADE) | 1:1 이므로 FK 가 곧 PK |
| `crude_protein_pct` | REAL | CHECK `0~100` | 조단백(%). 신장 관리식(고단백 회피) |
| `crude_fat_pct` | REAL | CHECK `0~100` | 조지방(%). 다이어트/췌장 |
| `crude_fiber_pct` | REAL | CHECK `0~100` | 조섬유(%). 포만감·배변 |
| `crude_ash_pct` | REAL | CHECK `0~100` | 조회분(%). 무기물 총량. 신장 관리식 판단에서 인·칼슘과 함께 본다 |
| `moisture_pct` | REAL | CHECK `0~100` | 수분(%). 건식/습식의 실제 근거 |
| `calcium_pct` | REAL | CHECK `0~100` | 칼슘(%). 성장기 골격 |
| `phosphorus_pct` | REAL | CHECK `0~100` | 인(%). 신장 관리식은 인을 제한한다 |
| `sodium_pct` | REAL | CHECK `0~100` | 나트륨(%). 심장/신장 |

### 설계 노트

**1:1 인데도 분리하는 이유는 결측이다.** 사료는 성분표가 있고 간식은 없는 경우가 흔하다.
`products` 에 NULL 컬럼 8개가 늘어서는 것보다 **값이 있는 제품만 행이 있는** 형태가 낫다.

**수치로 저장한다.** 태그 문자열(`'저인'`)로는 "인 함량 3% 이하"를 고를 수 없다.

---

## product_feeding_purposes

제품 ↔ 급여목적 (다대다). 제품 하나가 '관절 + 다이어트'처럼 복수 목적을 갖는다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `product_id` | INTEGER | PK, FK → [`products`](#products) (CASCADE) | 제품 |
| `feeding_purpose_id` | INTEGER | PK, FK → [`feeding_purposes`](#feeding_purposes) (RESTRICT) | 급여목적 |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| (복합 PK) | (`product_id`, `feeding_purpose_id`) | 중복 등록 차단 + "이 제품의 목적들" |
| `idx_prod_fp_purpose` | (`feeding_purpose_id`) | "이 목적의 제품 전부" — 후보군 좁히기가 이 방향으로 탄다 |

[`pet_breeds`](pet_schema.md#pet_breeds) 와 같은 구조다 — 대리키 없이 복합 PK, `WITHOUT ROWID`.
목적이 없는 제품(공용)은 행이 0개다.

---

## ingredients

원료 마스터. **알러지 판정의 연결 고리다.** 실제 매핑은
[`ingredient_allergens`](#ingredient_allergens) 가 갖는다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `ingredient_id` | INTEGER | PK | 대리키 |
| `name_ko` | TEXT | NOT NULL, UNIQUE | 원료명. 예: `'닭가슴살'`, `'계육분'`, `'연어'` |

### 설계 노트

**이 테이블이 존재하는 이유는 문자열 매칭을 없애기 위해서다.** `'닭가슴살'`·`'계육분'`·`'치킨오일'`
은 서로 하나도 안 닮았지만 전부 `닭고기` 한 알러지원을 가리킨다. 양쪽이 같은 알러지원 id 를
참조해야 판정이 문자열 비교가 아니라 **조인**이 된다.
반대편은 [`pet_allergies`](pet_schema.md#pet_allergies) 다.

**원료 단위 검토 플래그는 두지 않는다 (2026-08-24 결정).** 이전에는 `allergen_reviewed` 로
"매핑 0행 = 알러지원 없음"과 "매핑 0행 = 아직 안 봄"을 갈라놨지만, 원료마다 사람이 확인하고
플래그를 올리는 운영 부담이 실익보다 컸다. 지금은 **매핑 0행을 알러지원 없음으로 본다.**

판정불가 판단은 제품 단위 [`products.ingredients_verified`](#products) 하나로만 한다.
그래서 fail-closed 가 걸리는 층이 원료가 아니라 **제품**이다 — 원료표를 옮겨 적은 제품이라면,
그 원료의 알러지원 매핑이 비어 있어도 '안전'으로 통과한다.
매핑 누락을 막는 것은 이제 등록 절차의 책임이다 ([`../docu.md`](../docu.md)).

---

## ingredient_allergens

원료 ↔ 알러지원 (다대다). **알러지 배제 판정이 실제로 조인하는 테이블이다.**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `ingredient_id` | INTEGER | PK, FK → [`ingredients`](#ingredients) (CASCADE) | 원료 |
| `allergen_id` | INTEGER | PK, FK → [`allergens`](common_schema.md#allergens) (RESTRICT) | 알러지원 |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| (복합 PK) | (`ingredient_id`, `allergen_id`) | 중복 등록 차단 + "이 원료의 알러지원들" |
| `idx_ing_allergen_allergen` | (`allergen_id`) | "이 알러지원에 해당하는 원료 전부" — 배제 필터가 이 방향으로 탄다 |

### 설계 노트

**컬럼 하나(`ingredients.allergen_id`)로 두면 fail-open 이라 분리했다.** 복합 원료는 알러지원을
여러 개 갖는다 — `'베이커리 부산물'` 은 밀·계란·유제품이다. 컬럼이 하나면 밀만 적히고
**계란과 유제품은 조용히 '안전'으로 통과한다.**
[`v_product_safety`](#v_product_safety) 의 '위험' 분기가 그 원료를 못 잡는다.

**[`allergens`](common_schema.md#allergens) 트리로 접히지도 않는다.** 가금류처럼 공통 조상이 있으면
상위 노드 하나로 대신할 수 있지만, 밀/계란/유제품은 공통 조상이 루트뿐이라 접으면
"모든 알러지"가 되어버린다.

**0행은 '알러지원 없음'으로 읽힌다.** 아직 안 본 원료와 구별되지 않는다 —
`allergen_reviewed` 를 뺀 대가다(2026-08-24). 매핑을 빠뜨리면 그 원료는 조용히 통과하므로,
원료 등록 시 매핑을 같이 넣는 것이 절차로 강제돼야 한다.

---

## product_ingredients

제품 ↔ 원료 (다대다). **알러지 배제 필터가 실제로 조인하는 테이블이다.**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `product_id` | INTEGER | PK, FK → [`products`](#products) (CASCADE) | 제품 |
| `ingredient_id` | INTEGER | PK, FK → [`ingredients`](#ingredients) (RESTRICT) | 원료 |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| (복합 PK) | (`product_id`, `ingredient_id`) | 중복 등록 차단 + "이 제품의 원료들" |
| `idx_prod_ing_ingredient` | (`ingredient_id`) | "이 원료를 쓴 제품 전부" |

### 설계 노트

**배합 순서(`position`)나 주단백질 여부를 두지 않는다.** 판정을 **포함/미포함 이진**으로
단순화하는 것이 안전하다. 알러지원이 하나라도 들어 있으면 **부분 감점이 아니라 배제**이므로
순서를 알아도 판정이 달라지지 않고, 순서 데이터 확보도 현실적으로 어렵다.

---

## v_product_safety

반려동물 × 제품 알러지 판정. **추천 파이프라인의 첫 단계이자, 판정 로직이 있는 유일한 곳이다.**

| 컬럼 | 설명 |
|---|---|
| `pet_id` | 반려동물 |
| `product_id` | 제품 |
| `verdict` | `WARN`(위험) / `None`(판정불가) / `Safe`(안전) |

**행의 범위** — 판매중(`is_active = 1`)이고 대상 축종이 맞는 제품 × 활동중(`inactive_at IS NULL`)인
반려동물 조합. 축종은 [`product_animal_categories`](#product_animal_categories) 에 이 아이의 축종이
등록돼 있어야 통과한다 (미등록 제품은 아예 행이 생기지 않는다).

### 판정이 2분법이 아니라 3분법인 이유

`NOT EXISTS` 하나로 안전/위험을 가르면 **"알러지원이 없다"와 "확인한 적이 없다"가 같아진다.**
원료가 등록되지 않은 제품이 `NOT EXISTS` 를 그냥 통과해 '안전'이 되므로,
**데이터가 부실할수록 더 안전해 보이는** — 방향이 반대인 실패가 생긴다.

| 판정 | 조건 | 처리 |
|---|---|---|
| `WARN` | 제품 원료 중 이 아이의 알러지원이 확인됨 | 후보에서 **완전히 제외**(감점이 아니다) |
| `None` | [`products.ingredients_verified`](#products) `= 0` — 원료표를 옮겨 적은 적이 없다 | 모르는 것을 안전으로 처리하지 않는다 |
| `Safe` | 원료표 확인 완료 + 알러지원 없음 | 통과 |

**fail-closed 가 걸리는 층은 제품 하나뿐이다 (2026-08-24).** 원료 단위 검토 플래그
`ingredients.allergen_reviewed` 를 뺐으므로, "원료표는 다 옮겨 적었지만 `'계육분'`의 알러지원
매핑이 비어 있다"는 상태는 이제 `Safe` 로 통과한다. 그 구멍은 등록 절차가 막는다.

**배제를 LLM 이 아니라 SQL 이 하는 이유는 결정성이다.** LLM 은 확률적으로 실패하지만
`NOT EXISTS` 는 반드시 배제한다. 임베딩 텍스트에 알러지 정보를 넣어도 벡터 유사도는
하드 조건을 보장하지 못한다.

---

## v_safe_products

추천 후보군. [`v_product_safety`](#v_product_safety) 에서 `verdict = 'Safe'` 만 통과시킨다.

| 컬럼 | 설명 |
|---|---|
| `pet_id` | 반려동물 |
| `product_id` | 통과한 제품 |

**`None`(판정불가)을 경고와 함께 후보에 넣는 정책으로 바꾸려면 이 뷰만 고친다.**
판정 로직 자체는 `v_product_safety` 한 곳에만 있다.
