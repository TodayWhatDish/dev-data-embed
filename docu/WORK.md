## 작업일지

## 2026-08-24

### `ingredients.allergen_reviewed` 제거 — 판정불가를 제품 한 층으로 줄였다

2026-08-17 에 넣었던 원료 단위 검토 플래그를 뺐다. `v_product_safety` 의 ③분기
("원료 중 `allergen_reviewed = 0` 인 것이 있으면 판정불가")도 같이 사라졌다.

**뺀 이유.** 이 플래그가 값을 하려면 원료 하나하나를 사람이 열어 보고 매핑을 넣은 뒤
플래그를 올려야 한다. 안 올리면 그 원료가 든 제품 전부가 영영 후보에서 빠지므로,
운영이 밀리는 순간 추천 결과가 통째로 비는 구조였다. 안전을 얻는 대신 **서비스가 안 도는**
쪽으로 실패하는 값이고, 그 운영 부담을 감당할 인력 계획이 없다.

**대신 잃은 것 (fail-open 이 생긴 자리).** `ingredient_allergens` 0행이 이제
'알러지원 없음'으로 읽힌다. 원료표는 다 옮겨 적었지만(`ingredients_verified = 1`)
그중 `'계육분'`의 알러지원 매핑을 아직 안 넣은 제품은 **`Safe` 로 통과한다.**
CLAUDE.md 도메인 규칙 2번("모르는 것을 안전으로 처리하지 않는다")이 원료 층에서는
더 이상 성립하지 않는다 — 제품 층(`ingredients_verified`)에만 남았다.
막는 책임은 DB 에서 등록 절차로 넘어갔고 `docu/docu.md` §1 에 적었다.

되돌릴 때는 컬럼 + ③분기 + 백필(`UPDATE ingredients SET allergen_reviewed = 1
WHERE ingredient_id IN (SELECT ingredient_id FROM ingredient_allergens)`) 세 가지가 필요하다.

**같이 고친 것** — 편집 중이던 `product_schema.py` 가 깨져 있었다.

- `WHERE ... IS NULL - 판매 물품` 의 `-` 가 `--` 여야 했다. `CREATE VIEW` 가 문법 오류로 실패했다.
- verdict 값을 `위험/판정불가/안전` → `WARN/None/Safe` 로 바꿨는데 `v_safe_products` 는
  `verdict = '안전'` 그대로였다. 에러 없이 **항상 0행**이 되는 상태였다.
  `'Safe'` 로 맞추고 `docu/schema/product_schema.md` 의 값 표기도 새 값으로 갱신했다.

**검증**

- `py src/create_schema/execute_schema.py` → 16 테이블 + 2 뷰 + 12 인덱스. `check_fk_targets()` 통과.
- 펫 10,000 × 제품 5,000 합성 데이터로 `v_safe_products` 조회:
  `WHERE pet_id = ?` 5.89ms / 필터 없음 56초 — 뷰는 `pet_id` 를 반드시 걸고 써야 한다
  (옵티마이저가 `pets` PK 로 푸시다운하는 것을 `EXPLAIN QUERY PLAN` 으로 확인).
  ③분기가 제품마다 도는 상관 서브쿼리였으므로 제거로 이 5.89ms 도 같이 줄었다.

### `src/sqlbench.py` 추가 — 변형 대조 벤치

위 5.89ms 를 더 줄일 수 있는지 보려고 쿼리를 몇 가지로 고쳐 썼는데, **매번 결과가 같은지
눈으로 대조하는 게 실수의 원인**이었다. 결과가 다른 쿼리를 "빠르다"고 고르면 벤치가 통째로 무의미하다.
stdlib `timeit` 은 시간만 재고 결과는 안 본다. 그래서 그 한 가지만 하는 모듈을 만들었다.

- `compare(con, variants, ...)` — 첫 변형의 결과를 기준으로 나머지를 `sorted()` 비교,
  다르면 `AssertionError` 로 멈춘다. 통과한 것만 시간을 잰다.
- 대표값은 **중앙값**이다. 평균은 첫 실행의 캐시 미스 한 번에 통째로 끌려간다.
- `elapsed_time` 컨텍스트 매니저는 `__exit__` 가 `False` 를 반환한다 — 블록에서 난 예외를
  삼키면 실패한 벤치가 성공으로 보인다. self-check 가 이 한 가지를 직접 검사한다.

**측정** (펫 10,000 × 제품 5,000, `pet_id` 지정, n=50 중앙값)

| 변형 | 중앙값 |
|---|---|
| `v_safe_products` | 5.62 ms |
| 비상관 서브쿼리 버전 | 2.20 ms |

(위 5.89ms 와는 별도 실행이라 뷰 숫자가 조금 다르다. 비교는 같은 실행 안에서만 유효하다.)

뷰가 느린 이유는 `EXISTS` 안에 `pa.pet_id = pt.pet_id` 가 있어서다 — 상관 서브쿼리라
후보 제품마다 알러지 조인을 새로 돈다. 펫 쪽 조건을 바깥 행을 참조하지 않는 서브쿼리로 빼면
SQLite 가 각각 한 번만 평가하고 결과에 자동 인덱스를 붙인다
(`EXPLAIN QUERY PLAN` 에 `CREATE BLOOM FILTER` 가 뜬다).

**최적화 쿼리는 커밋하지 않는다.** 같은 판정 로직의 두 번째 사본이라 CLAUDE.md 도메인 규칙
1번("판정 로직은 `v_product_safety` 한 군데뿐")과 정면으로 어긋난다. 쓰는 앱 코드도 아직 없고,
3.4ms 차이가 지금 아픈 데가 없다. 뷰가 실제로 병목이 됐을 때 아래를 꺼내 쓰고,
그때 뷰와 대조하는 테스트를 같이 넣는다.

```sql
SELECT pac.product_id
  FROM product_animal_categories pac
  JOIN products pr ON pr.product_id = pac.product_id
 WHERE pac.animal_category_id = (SELECT animal_category_id
                                   FROM pets
                                  WHERE pet_id = ?1 AND inactive_at IS NULL)
   AND pr.is_active            = 1
   AND pr.ingredients_verified = 1
   AND pr.product_id NOT IN (
       SELECT pi.product_id
         FROM product_ingredients pi
         JOIN ingredient_allergens ia ON ia.ingredient_id = pi.ingredient_id
        WHERE ia.allergen_id IN (SELECT allergen_id
                                   FROM pet_allergies
                                  WHERE pet_id = ?1))
```

`?1` 은 번호 파라미터다. 같은 값을 두 군데 쓰므로 바인딩은 `(pet_id,)` 하나로 끝난다.

**경계 케이스** — 폐기 전에 뷰와 결과가 같음을 확인한 것들: 알러지 0건 펫(`IN (빈 집합)` 이
FALSE 라 `NOT IN` 이 전부 TRUE), 축종 미등록 제품(`product_animal_categories` 0행 → 제외),
`ingredients_verified = 0`, `is_active = 0`, `inactive_at` 이 찍힌 펫. 모두 뷰와 일치했다.
앱에서 `allergen_id` 목록을 꺼내 f-string 으로 `IN (?,?,?)` 를 조립하는 방식은 알러지 0건에서
`IN ()` 이 되어 문법 오류가 난다 — 목록을 앱으로 가져오지 않는 이유다.

## 2026-08-17

### B블록(제품) 스키마 추가 — `src/create_schema/create_schema.py`

A블록(보호자/반려동물) 7테이블에 이어 제품 8테이블 + 뷰 2개를 붙였다. **현재 15 테이블 + 2 뷰.**
컬럼 설명은 `docu/schema/` (색인은 `docu/schema/README.md`).

추가: `product_categories`, `feeding_purposes`, `products`, `product_animal_categories`,
`product_nutrition`, `product_feeding_purposes`, `ingredients`, `product_ingredients`,
`v_product_safety`, `v_safe_products`.

**옛 초안(`src/make_db/create_db_schema.py`)에서 바뀐 것**

- **대상 체구/연령 → min/max 범위 컬럼.** `pets.size` 가 정수 1~5 가 되면서
  `target_size TEXT IN ('소형','중형','대형','전체')` 을 쓸 수 없게 됐다.
  `target_size_min/max`(1~5), `target_age_min_month/max_month` 로 바꿨다.
  `'전체'` 라는 마법값이 사라지고 필터가 `BETWEEN` 하나로 끝난다.
  NOT NULL + DEFAULT(1/5, 0/1200)인 이유는 NULL 이면 `BETWEEN` 이 NULL 로 평가되어
  그 제품이 조용히 후보에서 빠지기 때문.
  연령을 등급이 아니라 월령으로 둔 이유는 시니어 기준이 축종·체구마다 다르기 때문(대형견 6세,
  소형견 9세, 고양이 11세).
- **`product_animal_categories` 신설.** A블록에서 `animal_categories` 가 생겨 고양이 제품이
  개 후보에 섞이는 문제가 새로 생겼다.
  처음엔 `products.animal_category_id INTEGER NULL`(NULL = 전 축종 공용)로 넣었다가
  같은 날 연결 테이블로 갈아탔다 — 아래 참조.
- **`category`/`sub_category` TEXT CHECK → `product_categories` 코드표(`parent_id` 계층).**
  `animal_categories` 와 같은 근거 — CHECK 은 테이블 재생성, 코드표는 INSERT 한 줄.
  사료 소분류는 시드하지 않는다(`'건식사료'`·`'퍼피사료'` 는 `food_form`·`target_age_*` 와 중복).
- **연결 테이블 2종을 복합 PK + `WITHOUT ROWID` 로 전환** (A블록 규칙 2). 대리키와 UNIQUE 인덱스가
  사라졌다.

### 알러지 판정 구멍 — 해결

2026-08-13 에 미해결로 남긴 `ingredients.allergen_id IS NULL` 이 "검토 후 알러지원 아님"과
"미검토"를 뭉개던 문제.

- `ingredients.allergen_reviewed` 추가 (NOT NULL DEFAULT 0).
  `CHECK (allergen_id IS NULL OR allergen_reviewed = 1)` — 매핑을 넣었다는 것 자체가 검토했다는 뜻.
- `v_product_safety` 의 '판정불가' 조건에 **미검토 원료 존재**를 추가.
  이전에는 "원료는 다 옮겨 적었지만 그중 `'계육분'` 이 무슨 알러지원인지 아무도 안 봤다"가
  '안전'으로 통과했다.

**검증** (`ingredients_verified` 와 `allergen_reviewed` 는 층이 다르다 — 전자는 제품 원료표,
후자는 원료별 판정. 둘 다 통과해야 '안전')

- 제약 차단 7종 통과: `min > max` / 체구 6 / 미검토인데 매핑 있음 / `weight_g = 0` /
  INTEGER 컬럼에 `'삼만원'`(STRICT) / 없는 FK / 복합 PK 중복.
- `'계육분'` 이 문자열이 아니라 `allergen_id` 조인으로 닭 알러지에 걸림.
- 원료표는 등록됐지만 미검토 원료가 있는 제품 → `판정불가` (구멍 재현 실패 = 막힘 확인).
- 고양이 전용 제품이 개 프로필 후보에서 제외, 축종 NULL 제품은 포함.
- `price_per_100g` 순서 뒤집힘 재확인 (1.8kg 3만원 = 1,666원/100g > 5kg 6만원 = 1,200원/100g).

### 대상 축종 — NULL 컬럼에서 연결 테이블로 교체 (같은 날 재검토)

`products.animal_category_id NULL = 전 축종 공용` 은 **축종이 2개일 때만 우연히 성립**하는
설계였다. 리뷰에서 나온 반례: **"개·고양이는 되고 앵무새는 안 되는 제품"을 표현할 수 없다.**
축종을 하나 늘리면 기존 `NULL` 행 전부가 "새 축종에게도 준다"로 조용히 의미가 바뀐다.
`allergens` 가 평면 목록을 버린 이유와 같은 실패 — "전체를 골랐다"는 사실이 남지 않으면
나중에 추가된 항목을 판단할 수 없다.

`product_animal_categories(product_id, animal_category_id)` 복합 PK + `WITHOUT ROWID` 로 교체.
부수 효과 두 가지가 다 이득이었다.

- **0행이 fail-closed.** NULL 컬럼은 미입력이 곧 '전 축종 통과'라 데이터가 부실할수록 넓게
  노출됐다. 연결 테이블은 미등록 제품이 아무에게도 안 뜬다 — `ingredients_verified` 와 같은 방향.
- **필터가 더 빨라졌다.** `(= ? OR IS NULL)` 은 인덱스를 반만 타지만, 조인은
  `idx_prod_ac_category` 를 covering index 로 탄다(EXPLAIN QUERY PLAN 확인).

검증: 축종 3종(개/고양이/앵무새) × 제품 5종으로 개묘공용껌이 앵무새 후보에서 빠지고
전축종트릿은 셋 다에 뜨며 축종 미등록 제품은 아무에게도 안 뜨는 것 확인. 복합 PK 중복·FK 차단 확인.

### 보류한 것 — 근거를 남겨둔다

- **`product_category_id` 는 단일 FK 유지.** "사료 겸 간식"이 애매한 경우는 실제로 있으나
  (동결건조 큐브), 그 애매함의 실체는 분류가 아니라 **"이것만 먹여도 되느냐(완전균형사료)"**
  라는 영양 속성이다. 분류를 다대다로 만들어도 그 질문에는 답 못 하고 집계만 이중으로 센다.
  필요해지는 시점에 `is_complete_food` 를 추가한다.
- **장난감·용품 대응은 안 한다.** 지금 `products` 는 식품 전용이고, 물품을 넣을 때 실제로 걸리는
  컬럼은 `weight_g`(NOT NULL) 와 `price_per_100g`(GENERATED) 두 개뿐이다 — 나머지 식품 속성은
  이미 별도 테이블이라 행이 0개면 그만이다. **이 레포엔 마이그레이션이 없어서**(로더가 매 실행
  `DROP` 후 재구축, 운영 데이터 없음) 나중에 `product_food` 1:1 로 빼는 비용이 스크립트 수정 +
  재생성이 전부다. 요구사항도 데이터도 없는 지금 추상화하면 검증 안 된 구조만 남는다.
  옮길 컬럼 목록은 `docu/schema/product_schema.md#products` 에 적어뒀다.

### 문서 분할 — `docu/SCHEMA.md` → `docu/schema/` 5파일

832줄 한 파일이 읽기 힘들어 도메인별로 쪼갰다.

| 파일 | 담는 것 |
|---|---|
| `README.md` | 색인 + 파일 지도 + 관계도 + 이 스키마가 지키는 3원칙 |
| `common_schema.md` | `animal_categories`, `allergens` |
| `user_schema.md` | `users` |
| `pet_schema.md` | `breeds`, `pets`, `pet_breeds`, `pet_allergies` |
| `product_schema.md` | 제품 8테이블 + 뷰 2개 |

**`common_schema.md` 를 따로 둔 이유** — `animal_categories` 와 `allergens` 는 반려동물 쪽과 제품
쪽이 **같은 ID 를 참조해야만** 성립한다. 한쪽 도메인 파일에 넣으면 다른 쪽에서 읽을 때 왜 저기
있는지 알 수 없다. 이 두 표가 공유된다는 사실 자체가 스키마의 핵심(알러지 배제가 문자열이 아니라
조인인 이유)이라 파일 하나로 드러내는 편이 낫다.

**뷰 2개는 `product_schema.md` 에 뒀다.** `pets × products` 를 걸치지만 목적이 제품 필터링이다.

경로 참조를 전부 갱신했다 — `create_schema.py` 주석 17곳, `WORK.md` 2곳, `docu.md` 1곳.
`docu/SCHEMA.md` 는 삭제했다.

**검증** — 크로스링크 47개 앵커 전부 해석됨, 옛 경로 잔존 참조 0건,
`sqlite_master` 의 17개 객체 전부 문서화됨(유령 문서 0건), README 파일 지도와 실제 파일 일치.

### 문서 ↔ 코드 대조 — 드리프트 6건 수정

`docu/schema/` 5파일과 `create_schema.py` 를 실제 생성 결과와 대조했다.
객체 수(15 테이블 + 2 뷰)와 인덱스 13개는 문서와 정확히 일치했고, 아래만 어긋나 있었다.

- **`idx_products_filter` 설명이 틀렸다.** `(is_active, product_category_id)` 에서
  `product_category_id` 는 뒤 컬럼이라 단독 조회가 SEARCH 가 아니라 **커버링 인덱스 SCAN** 이다
  (`EXPLAIN QUERY PLAN` 확인). "선두 컬럼이 FK 인덱스를 겸한다"는 서술을 실제 동작과
  단독 인덱스를 두지 않는 진짜 이유(부모가 시드 5행이라 삭제 검사가 거의 없음)로 교체.
- `create_schema.py` 규칙 6 의 불리언 목록이 낡아 있었다 — 없는 `reviews.is_holdout` 이 있고
  실재하는 `ingredients_verified`·`allergen_reviewed` 가 빠져 있었다.
- `common_schema.md` 의 `CHECK (animal_category IN (1,2))` → `animal_category_id`.
- `pet_schema.md` 의 "`animal_category_id` 를 **갖게 될** 테이블" → 이미 존재하므로 현재형 + 링크.
- 문서 분할 기록의 "주석 16곳" → 실제 17곳.
- **`DESIGN.md` 가 2026-08-13 에서 멈춰 있다.** `schema/README.md` 가 "왜"를 그쪽으로 넘기고
  있었는데, 규칙 2(다대다 = 대리키 + UNIQUE)가 지금 코드(복합 PK + `WITHOUT ROWID`)와 정반대다.
  README 의 안내를 각 파일 **설계 노트**로 돌리고 스테일 경고를 붙였다. 본문 갱신은 남은 것 참조.

### 코드 분할 — `create_schema.py` → `src/create_schema/` 5파일

470줄 한 파일을 `docu/schema/` 문서 구성과 **1:1 로** 맞춰 쪼갰다.

| 코드 | 문서 | 내용 |
|---|---|---|
| `execute_schema.py` | `schema/README.md` | 진입점 + 설계 규칙 전문 |
| `common_schema.py` | `schema/common_schema.md` | `animal_categories`, `allergens` |
| `user_schema.py` | `schema/user_schema.md` | `users` |
| `pet_schema.py` | `schema/pet_schema.md` | `breeds`, `pets`, `pet_breeds`, `pet_allergies` |
| `product_schema.py` | `schema/product_schema.md` | 제품 8테이블 + 뷰 2개 |

**모듈 계약** — 각 모듈은 `TABLES` / `INDEXES` / `UNIQUE_INDEXES` / `VIEWS` / `SEEDS` 를
**있는 것만** 모듈 수준 리스트로 노출한다. `execute_schema.collect()` 가 `MODULES` 순서대로
이어붙여 실행한다. 함수로 감싸지 않은 이유는 DDL 이 그냥 데이터라서다 — 함수로 만들면
`return [...]` 한 줄이 늘 뿐이다.

`MODULES` 순서가 곧 생성 순서이고 의존을 담는다: common → user → pet → product.
product 가 맨 뒤인 이유는 뷰가 `pets`/`pet_allergies` 까지 읽기 때문이다 —
테이블의 FK 는 대상이 없어도 CREATE 가 되지만 뷰는 안 된다.

**분할하면서 고친 것 3가지**

- **DROP 목록을 없앴다.** `drop_all()` 이 `sqlite_master` 를 읽어 있는 것을 전부 지운다.
  모듈마다 DROP 목록을 두면 목록과 실제가 어긋나 유령이 남는데, **이미 겪은 버그다** —
  옛 스크립트의 `purchases`/`reviews`/`review_embeddings` 가 목록에 없어서 계속 살아남아
  객체 수가 17개로 잡혔었다. '무엇을 만들었나'가 아니라 '지금 무엇이 있나'를 보면 어긋날 수 없다.
- **`check_fk_targets()` 추가.** SQLite 는 없는 테이블을 가리키는 FK 로도 `CREATE TABLE` 을
  통과시킨다(검증에서 확인). `MODULES` 순서가 틀어지거나 테이블명에 오타가 나면 생성은 성공하고
  INSERT 할 때가 되어서야 터지므로, 생성 직후에 잡는다.
- **시드를 FK 검증이 켜진 상태로 넣는다.** 전에는 `foreign_keys = OFF` 인 채로 시드가 들어가
  `product_categories.parent_id` 같은 자기참조가 검사되지 않았다. `PRAGMA foreign_keys` 는
  트랜잭션 안에서 무시되므로 `commit()` 뒤에 켜고 시드를 넣는다.

`STRICT = ' STRICT'` 상수도 없앴다. 모듈 4개가 공유해야 하는데, docstring 이 "끄는 스위치를 두지
않는다"고 못 박은 값이라 스위치처럼 보이는 변수로 두는 것 자체가 오해를 만든다. DDL 에 그대로 적었고
그 덕에 f-string 도 전부 사라졌다.

**검증 — 분할 전후 스키마 동등성**

옛 `create_schema.py` 와 새 `execute_schema.py` 로 각각 DB 를 만들어 대조했다.

- 객체 30개(테이블 15 + 뷰 2 + 인덱스 13) 집합 일치, **DDL 본문 30개 전부 일치**(공백 정규화 후).
- 시드 3개 테이블(`animal_categories` 2행 / `product_categories` 5행 / `feeding_purposes` 6행) 행 일치.
- 새 안전장치 동작 확인: 유령 테이블 3개를 심어둔 DB 에서 전부 제거됨,
  `check_fk_targets` 가 없는 부모를 가리키는 FK 를 `RuntimeError` 로 잡음.

`create_schema.py` 는 삭제했다. 경로 참조 갱신: `README.md`, `CLAUDE.md`, `docu/docu.md`,
`docu/schema/` 5파일.

### 범위 확정 — 분류 겸용 없음 / 축종은 개·고양이 둘

**① '사료 겸 간식'을 고려하지 않는다.** 간식이면 간식, 사료면 사료로 무조건 하나를 고른다.
`product_category_id` 가 이미 단일 FK 라 **코드 변경은 없고** 문서의 여지를 결정으로 굳혔다.

대분류 판정이 실제로 쓰이려면 한 칸 올라가야 한다는 점을 명시했다 —
제품이 대분류(`사료`)를 직접 가리킬 수도, 소분류(`덴탈껌`)를 가리킬 수도 있기 때문이다.
계층이 2단계 고정이라 `COALESCE(c.parent_id, c.product_category_id)` 로 끝난다.
**다만 2단계 고정을 DB 가 강제하지 못한다** — 3단계가 생기면 손자가 자기 부모를 대분류로
보고해 에러 없이 틀린다. 운영 규칙으로 `docu.md` 에 넣었다.

**② 축종은 개(1)/고양이(2) 둘뿐.** 앵무새는 넣지 않는다 — `GOAL.md` 타겟은 반려견이고
고양이도 이미 GOAL 을 넘어선 확장이다. 축종을 늘리는 건 `animal_categories` INSERT 한 줄이지만
`breeds` 목록, `pets.size`/`body_type` 척도, 급여 기준이 전부 딸려 와야 의미가 있다.

**연결 테이블(`product_animal_categories`) 은 그대로 둔다.** 8/17 오전에 이걸 도입하며 든 근거
("개+고양이 되고 앵무새는 안 되는 제품을 NULL 로 표현 못 한다")는 **가장 약한 근거였다** —
축종이 정확히 둘이면 NULL 로도 '둘 다'가 표현된다. 실제로 유지해야 하는 이유는 축종 수와 무관한
아래 둘이고, 문서를 이 순서로 다시 썼다.

- **NULL 은 '공용'과 '미입력'을 구분 못 하고 fail-open 이다.** 축종 미입력 제품이 전 프로필에
  노출된다 — 데이터가 부실할수록 넓게 노출되는, 이 레포가 일관되게 막아온 방향의 반대.
  연결 테이블은 0행 = 아무에게도 안 뜸.
- **축종을 늘려도 기존 행의 뜻이 안 바뀐다.** NULL 방식은 셋째 축종이 들어오는 순간
  기존 NULL 행 전부가 "새 축종에게도 준다"로 조용히 바뀐다.

지금 표현해야 하는 조합은 셋뿐이고 전부 커버된다: 강아지 사료(1행) / 고양이 사료(1행) /
개·묘 공용(2행).

### `GOAL.md` 를 개·고양이로 갱신 — 스키마가 앞서 있던 불일치 해소

`GOAL.md` 는 "반려견을 키우는 사용자"만 말하는데 스키마는 고양이를 시드하고 있었다.
확인 결과 **고양이는 의도된 범위**였다. 요구사항 문서가 뒤처져 있던 것이라 `GOAL.md` 를 고쳤다.

- **'대상 축종' 절 신설** — 개·고양이 둘로 명시하고, 축종을 늘리는 것이 코드표 INSERT 문제가
  아닌 이유(품종 목록·체구/체형 척도·급여 기준이 전부 딸려 와야 함, BCS 5점 척도는 새에게 무의미)를
  적었다. 제품이 대상 축종을 **여러 개** 가질 수 있다는 요구사항도 여기 박았다 —
  `product_animal_categories` 가 이제 요구사항에 근거를 갖는다.
- 서비스 목적/타겟: "반려견", "애완견 물품" → 개·고양이, 반려동물 사료.
- 필요 데이터·예시 프로세스: "견종" → **"축종(개/고양이), 품종"**. 체구도 항목에 추가.
  축종이 알러지와 마찬가지로 **정형 필터(SQL)가 먼저 거르는 첫 관문**이라는 점을 명시했다.
- 2부 메시지: "강아지는 저마다 다릅니다" → 개·고양이를 함께 말하도록 고치고,
  "강아지 사료를 고양이에게 물어보는 일은 없어야 합니다" 한 줄을 넣었다.
- **명소 추천은 개 한정으로 명시.** 동반 카페·공원이 전제라 고양이에게 성립하지 않는다.
  추천 본체는 양쪽을 다루지만 명소는 축종으로 걸러 노출한다.
- `pet_purchases.is_holdout` → `reviews.is_holdout` (옛 4테이블 이름이 남아 있었다).

연쇄 갱신: `README.md`, `CLAUDE.md`(dog → pet + 범위 명시),
`docu/schema/common_schema.md`·`product_schema.md` 의 "GOAL 타겟은 반려견" 서술.

`docu/DESIGN.md`(반려견 표현 6곳)와 `src/src.md` 는 손대지 않았다 — 전자는 이미 스테일로
표시돼 있고, 후자는 개 전용 더미 데이터를 쓰는 **옛 파이프라인** 문서라 그 서술이 사실이다.

### `idx_products_filter` 컬럼 순서 교체 — 제품 단독 필터링

리뷰 지적: "`product_category_id` 로 **제품만으로 필터링**하는 조회가 있지 않나."
맞았다. 추천 경로(반려동물 프로필 조인)를 타지 않고 `WHERE product_category_id = ?` 만으로
제품 목록을 뽑는 조회가 따로 있는데, 기존 순서로는 그게 인덱스를 못 탔다.

`(is_active, product_category_id)` → **`(product_category_id, is_active)`** 로 교체.

| 조회 | `(is_active, cat)` | `(cat, is_active)` |
|---|---|---|
| `cat = ?` 단독 | **풀스캔** (ANALYZE 후 skip-scan) | **SEARCH** |
| `is_active = 1 AND cat = ?` | SEARCH | SEARCH (동일) |
| `is_active = 1` 단독 | SEARCH | skip-scan |

`is_active` 는 값이 `0`/`1` 뿐이라 통계가 있으면 skip-scan 이 붙지만,
**`execute_schema.py` 는 `ANALYZE` 를 돌리지 않아** 갓 만든 `user.db` 에는 통계가 없다.
즉 실제 상태에서 카테고리 단독 조회가 풀스캔이었다(`EXPLAIN QUERY PLAN` 으로 양쪽 확인).

두 컬럼 모두 등호인 후보군 필터는 순서와 무관하게 동일하고, 잃는 건 `is_active` 단독 조회뿐인데
그건 활성 제품 전부를 뽑는 것이라 인덱스가 의미 없다. 선두가 FK 가 되면서
부모행 삭제 검사도 이 인덱스가 겸하게 되어, "FK 단독 인덱스를 왜 안 만드나"라는 해명도 사라졌다.

**앞선 기록 정정** — 같은 날 문서 대조 때 "`product_category_id` 단독 조회는 커버링 인덱스
SCAN 이다"라고 적었는데, 정확히는 통계 유무에 따라 갈린다(없으면 풀스캔 / 있으면 skip-scan SEARCH).
순서를 뒤집으면서 이 구분 자체가 무의미해졌다.

### 주의 — 실행 인터프리터

`python`(PATH, 3.9)은 **SQLite 3.35.5** 라 STRICT 테이블을 파싱하지 못한다.
`py`(3.12, SQLite 3.49.1)로 실행해야 한다. `py src/create_schema/execute_schema.py`.

### 남은 것

C블록(`purchases`/`reviews`)과 D블록(`review_embeddings`)은 아직 새 스키마로 안 옮겼다.
`user.db` 에 남아 있던 옛 스크립트 산출물(`purchases`/`reviews`/`review_embeddings`/`v_pet_context`/
`v_review_docs`)은 새 스키마의 DROP 목록에 없어 유령으로 남아 있었고, DB 를 지우고 재생성했다.

**`docu/DESIGN.md` 본문 갱신.** 지금 어긋나는 곳: 파일 경로(`src/make_db/create_db_schema.py`),
규칙 2(다대다 대리키 → 복합 PK), 인덱스 원칙의 `uq_pet_allergen`(없는 인덱스), 테이블 수(14 → 15)와
관계도·테이블 목록(축종/분류 코드표 누락), 알러지 3분법 표의 `[미해결]` 박스(오늘 해결됨),
뷰 4개(→ 2개). C블록까지 옮긴 뒤 한 번에 다시 쓴다.

## 2026-08-13

### DB 스키마 재설계 — `src/make_db/create_db_schema.py`

`data/*.csv`를 기준으로 삼지 않고 `docu/GOAL.md` 요구사항에서 역산해 스키마를 새로 짰다.
결과: **14 테이블 + 4 뷰**. 확정 내용은 `docu/DESIGN.md`.

**타입 확정** — CSV가 전부 TEXT라 조인·필터에 부적합했던 문제.
전 테이블 STRICT로 두고 PK를 `INTEGER PRIMARY KEY`(rowid 별칭)로 통일,
금액은 INTEGER(원), 실수는 REAL, 불리언은 INTEGER + `CHECK IN (0,1)`,
날짜는 TEXT ISO-8601 + `date()` CHECK.
(SQLite에 unsigned 타입은 없다. `uint64`는 STRICT에서 에러이고 비STRICT에서도 제약이 없다.)

**구조 변경**

- `'C0001'` TEXT PK → 정수 대리키
- `age` 정수 저장 → `birth_date` 저장 후 계산 (나이는 시간이 지나면 틀려지는 값)
- 구매/후기 한 테이블 → `purchases` / `reviews` 분리
- 알러지 문자열 매칭 → `allergens` 마스터 + `ingredients.allergen_id` 매핑
- 급여목적 단일 컬럼 → `feeding_purposes` + `product_feeding_purposes` (겸용 제품 표현)
- 벡터 JSON TEXT → BLOB (384차원 기준 4.5KB → 1.5KB)
- `brands` 테이블 제외 (자체 판매 B2C라 `products.brand` 텍스트로 충분)

**검증** — 알러지 배제가 `'닭가슴살'`·`'계육분'` 같이 서로 안 닮은 원료명에서도 동작함을 확인.
제약 차단 5종(중복 알러지 등록 / 별점 6점 / `'2026-13-99'` / INTEGER 컬럼에 `'삼만원'` / 없는 FK) 모두 통과.
`price_per_100g` 생성 컬럼으로 총액 기준 예산 비교의 순서 뒤집힘을 확인
(1.8kg 3만원 = 1,666원/100g vs 5kg 6만원 = 1,200원/100g).

### 알러지 판정 구멍 발견 — 일부 해결

`NOT EXISTS`가 "알러지원이 없다"와 "확인한 적이 없다"를 구분하지 못해,
**데이터가 부실할수록 더 안전해 보이는** 실패가 있었다.

- 해결: `products.ingredients_verified` 추가. 판정을 `위험/판정불가/안전` 3분법(`v_product_safety`)으로 변경.
- **미해결**: `ingredients.allergen_id IS NULL`이 "검토 후 아님"과 "미검토"를 뭉갠다.
  매핑이 비면 여전히 '안전'으로 통과. `allergen_reviewed` 플래그 필요 — `local/ToDo.md` §8-2.

### 결정 사항

- `neutered`는 저장하되 급여/추천 로직에는 쓰지 않기로 팀 협의.
  개체차가 커서 0/1로 정도를 표현할 수 없고, 결과는 `body_type`이 이미 담는다.
- 알러지에 심각도(`severity`)를 두지 않는다. 보호자가 안다는 것 자체가 겪어봤다는 뜻이므로 무조건 배제.
- 리뷰에서 추론한 알러지를 프로필로 승격시키지 않는다.

### 후속

`user.db` 재생성, `load_db.py` 재작성, 더미 CSV 재생성, `embed_reviews.py` 포팅.
상세는 `local/ToDo.md` §9.

## query.py

질문/체급/알레르기를 입력받아 프로필 조건으로 거른 벡터검색 결과를 보여주고 매 질문을 query_log.jsonl에 기록

## embed.py
config.py로 경로/모델명 분리, build_doc에 e5 전환 대비 "passage:\n" 접두어 추가(질의 쪽 "query:" 접두어는 아직 안 붙음, 모델도 아직 e5 아님).