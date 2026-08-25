# pet_schema.md — 반려동물

유저가 소유한 개체와, 그 개체를 설명하는 어휘.

| 테이블 | 설명 |
|---|---|
| [`breeds`](#breeds) | 품종 마스터 (읽기 전용) |
| [`pets`](#pets) | 반려동물 프로필. **유저가 소유한 개체** |
| [`pet_breeds`](#pet_breeds) | 반려동물 ↔ 품종 (다대다) |
| [`pet_allergies`](#pet_allergies) | 반려동물 ↔ 알러지원 (다대다). 추천의 하드 필터 |

축종(`animal_categories`)과 알러지원(`allergens`)은 제품 도메인과 공유하므로
[common_schema.md](common_schema.md) 에 있다. 보호자 계정은 [user_schema.md](user_schema.md).

> 전체 색인은 [README.md](README.md).
> 이 문서와 `src/create_schema/` 가 어긋나면 **코드가 맞다.**

---

## breeds

품종 마스터. 개/고양이 품종명을 한곳에 모아두는 정적 코드표다. **앱 기준 읽기 전용** — 관리자가 채운다.

한 마리가 여러 품종을 가질 수 있으므로 `pets` 가 이 테이블을 직접 참조하지 않고, 연결 테이블
[`pet_breeds`](#pet_breeds) 를 거친다. 품종을 모르는 개체는 `pet_breeds` 에 행이 0개다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `breed_id` | INTEGER | PK | 대리키 |
| `animal_category_id` | INTEGER | NOT NULL, FK → [`animal_categories`](common_schema.md#animal_categories) | 축종 |
| `name_ko` | TEXT | NOT NULL | 표준 품종명(한글) |
| `name_eng` | TEXT | | 품종명(영문). 표준 영문명이 없는 품종은 NULL |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| `uq_breeds_name_ko` | UNIQUE (`animal_category_id`, `name_ko`) | 한글명 중복 차단 + 종별 목록 조회 |
| `uq_breeds_name_eng` | UNIQUE (`animal_category_id`, `name_eng`) | **표기만 다른 같은 품종** 중복 차단 |

### 설계 노트

**체구/표준체중 컬럼을 두지 않는다.** 요즘 개체는 대부분 믹스라 품종 표준값이 개체에 들어맞지 않는다.

**이 테이블이 남아 있는 이유는 품종이 기호성 신호이기 때문이다.**
| 예시 |
|---|
|"포메가 잘 먹어요"|
|"시바는 별로 안 좋아하네요"|

같은 후기를 품종 단위로 묶으려면 개체의 품종 성분을 알아야 한다.
즉 체구를 알기 위한 테이블이 아니라, **후기를 품종으로 집계하기 위한 어휘**다.

**UNIQUE 를 한글·영문 양쪽에 건다.** 한글명에만 걸면 음차 표기가 갈린 같은 품종이 두 번 등록된다 —
`'코커스패니얼'` 과 `'코카스파니엘'` 은 서로 다른 문자열이라 한글 UNIQUE 를 그대로 통과한다.
영문 품종명은 AKC/FCI 기준으로 표준화되어 있어 **더 정규적인 식별자**이므로, 여기에 UNIQUE 를 걸면
같은 품종의 중복 등록이 DB 레벨에서 막힌다.

`name_eng` 가 NULL 허용인데도 UNIQUE 를 걸 수 있는 이유는 SQL 이 NULL 을 서로 다른 값으로 보기
때문이다. 표준 영문명이 없는 품종은 NULL 로 여러 행이 공존한다.

| INSERT | 결과 | |
|---|---|---|
| `'코커스패니얼'` + `'Cocker Spaniel'` | 등록 | |
| `'코카스파니엘'` + `'Cocker Spaniel'` | **차단** | 한글은 다르지만 영문이 같다 |
| `'진돗개'` + NULL | 등록 | |
| `'삽살개'` + NULL | 등록 | NULL 끼리는 충돌하지 않는다 |

**둘 다 `animal_category_id` 를 앞에 둔 복합 인덱스다.** 품종 선택 드롭다운을 채우는 조회
(`WHERE animal_category_id = ? ORDER BY name_ko`)가 leftmost prefix 로 `uq_breeds_name_ko` 를
그대로 탄다. `uq_users_auth` 와 달리 여기서는 컬럼 순서가 실제로 이득을 만든다.

**축종은 [`animal_categories`](common_schema.md#animal_categories) 를 참조한다.** 코드값의 뜻은 그
표에 있다. `animal_category_id` 를 갖는 다른 테이블([`pets`](#pets), [`product_animal_categories`](product_schema.md#product_animal_categories))도
같은 테이블을 참조해야 한다 — 테이블마다 코드를 따로 매기면 조인과 필터가 에러 없이 조용히 틀린다.

**'믹스' / '모름' 행을 만들지 않는다.** `size_category` 가 없어진 지금은 값을 하나 고를 필요도
없어졌지만, 애초에 품종을 모르는 상태는 `pet_breeds` 의 행 0개로 표현하는 것이 맞다.

---

## pets

반려동물 프로필. 추천의 정형 입력이 여기 모인다. **유저가 소유한 개체**이며
[`users`](user_schema.md#users) 를 `user_id` FK 로 참조한다(1 보호자 : N 반려동물).

**오래 변하지 않는 속성만 넣는다.** 그때그때 달라지는 상태("요즘 변이 무르다", "이가 안 좋아져서
습식으로 바꿨다")는 요청 단위 자연어로 받고 프로필에 저장하지 않는다. 프로필에 두면 다음 입력이
이전 값을 덮어써서 이력이 사라지고, 값이 낡았을 때 조용히 틀린 필터가 된다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `pet_id` | INTEGER | PK | 대리키 |
| `user_id` | INTEGER | NOT NULL, FK → [`users`](user_schema.md#users) (CASCADE) | 보호자. 1 보호자 : N 반려동물 |
| `animal_category_id` | INTEGER | NOT NULL, FK → [`animal_categories`](common_schema.md#animal_categories) | 축종 |
| `name` | TEXT | NOT NULL | 이름. LLM 응답에서 이름을 불러주는 데 쓴다 |
| `gender` | TEXT | CHECK `M`/`F` | 성별 |
| `birth_date` | TEXT | CHECK date | 생년월일. 나이는 조회 시점에 계산한다 |
| `weight_kg` | REAL | CHECK `> 0` | 현재 체중. 급여량·칼로리 계산의 기준 |
| `size` | INTEGER | CHECK `1~5` | 체구(보호자 판단). **`1` 초소형 / `2` 소형 / `3` 중형 / `4` 대형 / `5` 초대형** |
| `body_type` | INTEGER | CHECK `1~5` | 체형(보호자 관찰). **`1` 여윔 / `2` 저체중 / `3` 이상적 / `4` 과체중 / `5` 비만** |
| `neutered` | INTEGER | CHECK `0`/`1` | 중성화 여부 |
| `inactive_at` | TEXT | CHECK datetime | 사망·파양 등으로 활동이 끝난 시각. NULL = 활성 |
| `created_at` | TEXT | NOT NULL, DEFAULT `datetime('now')` | 등록 시각 |
| `updated_at` | TEXT | NOT NULL, DEFAULT `datetime('now')` | 마지막 수정 시각 |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| `idx_pets_user` | (`user_id`) | 보호자의 반려동물 목록 조회 |

### 설계 노트

**`size` / `weight_kg` / `body_type` 은 서로 다른 질문에 답한다.** 겹치지 않으므로 값이 서로
어긋나도 상관없고, 교차 CHECK 도 걸지 않는다 — 정상적인 경계 케이스까지 막힌다.

| 컬럼 | 답하는 질문 | 쓰임 |
|---|---|---|
| `size` | 얼마나 큰가 | `products.target_size_min`/`max` 매칭 (필터) |
| `weight_kg` | 몇 kg인가 | 급여량·칼로리 (수치 계산) |
| `body_type` | 살쪘나 | 다이어트 제품 (필터) |

30kg 대형견도 마를 수 있고 5kg 소형견도 비만일 수 있다. 품종상 소형견이어도 실제로 크게 자랐으면
보호자가 `4`(대형)를 고른다 — 품종 표준이 아니라 **눈앞의 개체**를 기준으로 입력받는다.

**`size` 와 `body_type` 은 정수 코드다.** 두 컬럼 모두 순서가 의미의 전부라 정수여야 범위 조회가
성립한다 — `WHERE size >= 3`("중형 이상"), `WHERE body_type >= 4`("과체중 이상 → 다이어트 사료").
TEXT 였다면 `'대형' > '소형'` 이 사전순 비교가 되어 무의미해진다.

`body_type` 의 5단계는 임의 구분이 아니라 **수의학의 BCS(Body Condition Score) 5점 척도**와 같다.
나중에 "갈비뼈가 만져지나요" 같은 문진으로 값을 받게 되면 그대로 매핑된다.

[`products.target_size_min`/`max`](product_schema.md#products) 는 `size` 와 **반드시 같은 코드**를
써야 한다 — 다르게 매기면 필터가 에러 없이 틀린다.

**`birth_date` 를 저장하고 나이는 계산한다.** `age` 정수를 저장하면 시간이 지나면서 조용히 틀려진다.

**`neutered` 는 보관하되 급여/추천 로직의 입력으로 쓰지 않는다.** 중성화가 기초대사량을 낮추는 건
사실이나 개체차가 커서 0/1 로 정도를 표현할 수 없고, '살이 찌기 쉽다'는 결과는 `body_type` 이 이미
더 직접적으로 담고 있다. 보관하는 이유는 프로필 완성도와 향후 코호트 분석이다.

**`inactive_at` 은 불리언이 아니라 시각이다.** 행을 지우면 그 아이가 남긴 후기가 끊기므로 삭제하지
않는다. 불리언이면 "떠났다"만 남지만 시각이면 **언제** 떠났는지가 남아, 오래된 후기의 가중치를
조정하거나 "최근 1년 내 활동한 반려동물" 같은 집계를 할 수 있다. 비용은 같다.
'사망'이 아니라 `inactive` 인 이유는 파양·입양보냄도 포함하기 때문이다.
[`v_product_safety`](product_schema.md#v_product_safety) 는 `inactive_at IS NULL` 인 개체만 다룬다.

**연결 테이블로 참조하는 것** — 한 마리가 여러 개를 가질 수 있어 컬럼으로 담기지 않는다.

| 항목 | 테이블 |
|---|---|
| 품종 | [`pet_breeds`](#pet_breeds) |
| 알러지 | [`pet_allergies`](#pet_allergies) |

**비정형 입력으로 받는 것** — 프로필에 저장하지 않고 요청 시점 자연어로 받는다.

- 급여 형태 (건식/습식)
- 식성 (식탐많음/식이까다로움)
- 급여목적 (관절/다이어트/피부) — 제품 쪽만 정형으로 관리한다.
  이유는 [`feeding_purposes`](product_schema.md#feeding_purposes) 참고.

---

## pet_breeds

반려동물 ↔ 품종 (다대다). 한 마리가 여러 품종 성분을 가질 수 있으므로 `pets` 에 `breed_id` 컬럼을
두지 않고 이 테이블을 거친다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `pet_id` | INTEGER | PK, FK → [`pets`](#pets) (CASCADE) | 반려동물 |
| `breed_id` | INTEGER | PK, FK → [`breeds`](#breeds) (RESTRICT) | 품종 |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| (복합 PK) | (`pet_id`, `breed_id`) | 중복 등록 차단 + "이 반려동물의 품종들" |
| `idx_pet_breeds_breed` | (`breed_id`) | "이 품종을 가진 반려동물 전부" — 품종별 후기 집계 |

### 설계 노트

**품종 수가 곧 행 수다.**

| 행 수 | 뜻 |
|---|---|
| 0 | 품종을 모른다 (잡종 포함) |
| 1 | 순혈 |
| 2 이상 | 믹스 |

"모름"을 NULL 이나 '믹스' 마법값으로 표현하지 않고 **행이 없는 상태**로 둔다. 아는 만큼만 등록하면 된다.

**비율 컬럼을 두지 않는다.** DNA 검사를 하지 않은 보호자의 "반반쯤?" 이 실측값 자리에 앉게 된다.
측정할 수 없는 정도를 숫자로 굳히지 않는다는 점에서 `pets.neutered` 와 같은 판단이다.
DNA 검사를 연동하는 날 컬럼을 추가하면 된다.

**대리키 없이 복합 PK 다.** `WITHOUT ROWID` 라 PK 가 곧 테이블의 클러스터 키이고, 중복 등록 차단도
PK 가 겸한다. 컬럼 2개에 인덱스 2개(PK + 역방향)로 끝난다.

**FK 방향이 다르다.** `pet_id` 는 CASCADE(반려동물이 지워지면 품종 연결도 정리), `breed_id` 는
RESTRICT(품종 마스터는 참조되는 한 지워지지 않는다).

**축종 정합성은 DB 가 막지 않는다.** 개인 `pet` 에 고양이 품종을 연결해도 제약에 걸리지 않는다.
앱이 품종 드롭다운을 `animal_category_id` 로 필터해서 채우는 것으로 방지한다.
DB 레벨에서 막으려면 양쪽에 `animal_category_id` 를 복합 FK 로 걸어야 하는데, 컬럼 하나와
UNIQUE 인덱스 두 개가 늘어 지금은 채택하지 않았다.

---

## pet_allergies

반려동물 ↔ 알러지원 (다대다). **추천의 하드 필터 입력이다.**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `pet_id` | INTEGER | PK, FK → [`pets`](#pets) (CASCADE) | 반려동물 |
| `allergen_id` | INTEGER | PK, FK → [`allergens`](common_schema.md#allergens) (RESTRICT) | 알러지원 |

**인덱스** — 복합 PK 하나뿐이다.

### 설계 노트

**카테고리를 고르면 하위를 전부 펼쳐 넣는다. 고른 카테고리 행도 같이 남긴다.**
목록 계산은 앱이 한다 — [`allergens`](common_schema.md#allergens) 트리는 UI 때문에 어차피 메모리에 있다.

`가금류` 를 고른 경우:

| `pet_id` | `allergen_id` | |
|---|---|---|
| 초코 | 가금류 | ← 고른 것 |
| 초코 | 닭고기 | ← 펼친 것 |
| 초코 | 오리 | ← 펼친 것 |

카테고리 행이 남아 있어야 나중에 `거위` 가 추가됐을 때 대상을 찾을 수 있다.

```sql
INSERT OR IGNORE INTO pet_allergies(pet_id, allergen_id)
SELECT pet_id, :new_id FROM pet_allergies WHERE allergen_id = :parent_id;
```

**제품 배제 필터의 입력이다.** 여기 있는 알러지원은 쿼리에서 예외 없이 배제된다.
실제 판정은 [`v_product_safety`](product_schema.md#v_product_safety) 가
[`ingredients.allergen_id`](product_schema.md#ingredients) 와 조인해서 내린다 — 문자열 비교가 아니다.

**심각도(`severity`)를 두지 않는다.** 보호자가 알러지를 안다는 것 자체가 이미 겪어봤다는 뜻이므로
무조건 배제한다. 반쯤 아는 심각도로 필터 강도를 조절하는 게 가장 위험하다.

**리뷰에서 추론한 알러지를 이 테이블에 넣으면 안 된다.** 추론값이 섞이면 안전한 제품이 잘못
배제되고, 보호자가 그 값을 사실로 믿는다. 추론 결과는 리뷰 쪽에만 남기고 프로필로 승격시키지 않는다.
