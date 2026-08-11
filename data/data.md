# AGENT.md — 추천 시스템용 더미 데이터셋

작성일: 2026-08-11

이 저장소는 **추천 시스템 포트폴리오용 더미 커머스 데이터셋**과 그 생성 스크립트입니다.
고객 300명 / 상품 600개 / 구매 1,500건이 서로 조인 가능한 5개 테이블로 구성돼 있습니다.

원본 참고 데이터는 [portfolio_dummy_data.csv](../portfolio_dummy_data.csv) (구매 800건, 4개 카테고리)이며,
이 파일의 `category` / `sub_category` / `user_trait` 값 체계를 그대로 승계했습니다.

---

## 1. 파일 구성

| 파일 | 역할 | 행수 | 생성 스크립트 |
|---|---|---|---|
| [customers.csv](../customers.csv) | 고객 마스터 | 300 | [generate_customers.py](../generate_customers.py) |
| [products_cosmetics.csv](../products_cosmetics.csv) | 상품 — 화장품 | 200 | [generate_products.py](../generate_products.py) |
| [products_pc_peripherals.csv](../products_pc_peripherals.csv) | 상품 — PC 주변기기 | 200 | 〃 |
| [products_healthwear.csv](../products_healthwear.csv) | 상품 — 신발 | 200 | 〃 |
| [purchases.csv](../purchases.csv) | 구매 트랜잭션 | 1,500 | [generate_purchases.py](../generate_purchases.py) |
| [portfolio_dummy_data.csv](../portfolio_dummy_data.csv) | 참고용 원본 (생성물 아님) | 800 | — |

모든 CSV는 **UTF-8 with BOM** 인코딩입니다 (Excel에서 바로 열림).
다중값 칼럼은 `|` 구분자를 씁니다 (예: `히알루론산|세라마이드|판테놀`).

---

## 2. 테이블 관계

```
customers (300)
    │ customer_id (PK)
    │
    │  skin_type      ─┐
    │  pc_user_type   ─┼─ 고객 속성 3종
    │  foot_type      ─┘
    │
    └──< purchases (1,500)
              │ purchase_id (PK)
              │ customer_id (FK → customers)
              │ product_id  (FK → products_*)
              │ category    ← 어느 상품 테이블인지 지시
              │
              └──> products_cosmetics       (P0001~P0200) target_skin_type
                   products_pc_peripherals  (P0201~P0400) target_user_type
                   products_healthwear      (P0401~P0600) target_foot_type
```

**핵심 설계**: 고객 속성 3종과 상품의 `target_*` 칼럼이 **같은 값 집합**을 씁니다.
따라서 `구매 → 고객속성 vs 상품타겟` 매칭 여부를 피처로 뽑을 수 있습니다.

| 카테고리 | 고객 칼럼 | 상품 칼럼 | 공통 값 |
|---|---|---|---|
| Cosmetics | `skin_type` | `target_skin_type` | 지성 / 건성 / 복합성 / 민감성 |
| PC_Peripherals | `pc_user_type` | `target_user_type` | 사무직 / 디자이너 / FPS유저 |
| Healthwear | `foot_type` | `target_foot_type` | 평발 / 발볼넓음 / 칼발 |

상품 쪽에는 특정 타입을 겨냥하지 않는 `공용` 값이 추가로 존재합니다 (화장품 70 / PC 46 / 신발 66건).

---

## 3. 스키마

### 3.1 customers.csv

| 칼럼 | 타입 | 설명 |
|---|---|---|
| `customer_id` | str | PK. `C0001` ~ `C0300` |
| `name` | str | 한글 이름. 성씨는 실제 인구 분포 가중, 300건 전부 유일 |
| `gender` | str | `F` 207 / `M` 93 (화장품 도메인 고려해 여성 비중 ↑) |
| `age` | int | 18~68, 평균 36.9. 20~30대 가중 |
| `phone` | str | `010-XXXX-XXXX`. 유일. 일부 011/016/017 |
| `email` | str | 이름 로마자 기반. 유일. naver 40% / gmail 30% / daum 12% 등 |
| `city` | str | 21개 시·도. 서울·경기 약 50% |
| `joined_at` | date | 2022-05-01 ~ 2026-06-19. 최근일수록 가입자 많음 |
| `skin_type` | str | Cosmetics용 속성 |
| `pc_user_type` | str | PC_Peripherals용 속성 |
| `foot_type` | str | Healthwear용 속성 |

**속성에 심어둔 상관관계** (완전 랜덤이면 분석 시 인사이트가 안 나오므로 의도적으로 부여):

- `skin_type` × 연령 — 29세 이하는 지성 최다(29/92), 45세 이상은 건성 최다(31/71)이고 지성은 4명까지 감소
- `pc_user_type` × 연령·성별 — 34세 이하 남성은 FPS유저 55%(28/51), 동연령 여성은 사무직·디자이너 중심
- `foot_type` — 연령·성별과 무관하게 균등 (실제로 상관이 약한 속성이라 의도적으로 평평하게)

### 3.2 products_*.csv

세 테이블이 동일한 골격을 쓰되 칼럼명만 도메인에 맞췄습니다.

| 공통 개념 | Cosmetics | PC_Peripherals | Healthwear |
|---|---|---|---|
| ID | `product_id` P0001~P0200 | P0201~P0400 | P0401~P0600 |
| 카테고리 | `category`, `sub_category` | 〃 | 〃 |
| 브랜드/상품명 | `brand`, `product_name` | 〃 | 〃 |
| 가격 | `price` | 〃 | 〃 |
| 용량/규격 | `volume_ml` | `weight_g` | `weight_g` + `size_range` |
| 대상 | `target_skin_type` | `target_user_type` | `target_foot_type` |
| 성분/사양 | `ingredients` | `key_specs` | `materials` |
| 우려 | `concerns` | `concerns` | `concerns` |
| 태그 | `tags` | 〃 | 〃 |
| 설명 | `description` | 〃 | 〃 |

**sub_category 구성**

| 카테고리 | 값 | 가격대 |
|---|---|---|
| Cosmetics | 보습 / 미백 / 진정 / 안티에이징 | 2,900 ~ 127,900원 (마스크팩 ~ 아이크림) |
| PC_Peripherals | 게이밍 마우스 / 게이밍 키보드 / 사무용 마우스 / 무선 이어폰 | 13,900 ~ 343,900원 |
| Healthwear | 런닝화 / 일상화 / 농구화 / 워킹화 | 50,900 ~ 287,900원 |

브랜드는 전부 **가상 브랜드명**입니다 (실존 브랜드에 허구의 스펙·가격이 붙는 것을 피하기 위함).

### 3.3 purchases.csv

| 칼럼 | 타입 | 설명 |
|---|---|---|
| `purchase_id` | str | PK. `O0001` ~ `O1500`. 구매일자 오름차순으로 부여 |
| `customer_id` | str | FK → customers |
| `product_id` | str | FK → products_* |
| `category` | str | `Cosmetics` / `PC_Peripherals` / `Healthwear` |
| `purchased_at` | date | 2022-08-02 ~ 2026-08-11. **항상 해당 고객의 `joined_at` 이후** |
| `quantity` | int | 1(74%) / 2 / 3 / 5 |
| `rating` | int | 1~5. 평균 4.09 |
| `review` | str | 후기. 62건(4%)은 빈 문자열 |
| `is_holdout` | int | 고객별 **마지막 구매** 1건만 1 → 정확히 300건 |

---

## 4. 데이터에 심어둔 신호와 규칙

### 4.1 속성 매칭 → 별점 (추천 모델 학습용 핵심 신호)

| 매칭 여부 | 건수 | 평균 별점 |
|---|---|---|
| 매칭 (고객 속성 == 상품 타겟) | 506 | **4.40** |
| 공용 상품 | 760 | 4.16 |
| 불일치 | 234 | **3.22** |

별점을 완전 랜덤으로 뽑으면 세 값이 같아져 모델이 학습할 게 없습니다.
`generate_purchases.py`의 `RATING_WEIGHTS`가 이 분포를 만듭니다.

### 4.2 구매 패턴

- 상품 선택의 65%는 고객 속성에 맞는(또는 공용) 상품에서, 나머지는 전체에서 선택 → 불일치 구매가 자연스럽게 섞임
- 상품별 인기도를 로그정규 분포로 부여 → 소수의 베스트셀러가 구매를 많이 가져가는 롱테일
- 고객마다 주력 카테고리가 있고 구매의 70%가 거기에 몰림
- 고객당 구매수 1건 / 중앙값 4건 / 최대 15건

### 4.3 후기 생성

문장 풀 조합 방식이라 1,500건 중 **1,028개가 서로 다른 문장**입니다
(참고파일은 카테고리당 4종류만 반복).

- 별점에 맞는 톤 — 1~2점 불만 / 3점 미지근 / 4~5점 만족
- 길이 편차 — `"만족합니다"` 한 줄부터 3~4문장까지 (중앙값 43자, 최대 123자)
- 배송·포장 언급 35%, 재구매 의사 40%, 이모지는 고평점의 25%
- 상품의 실제 `ingredients`/`concerns`/`sub_category`와 고객 속성을 문장에 끌어옴
  → `"복합성 피부인데 자극 없이 잘 맞았어요"`, `"스쿠알란 들어간 제품 찾고 있었는데 딱이네요"`

### 4.4 일관성 보정

랜덤 조합이 만들어내는 모순을 제거했습니다.

- **연결 방식 배타 처리** — `유선 연결`과 `2.4GHz 무선`이 한 상품의 `key_specs`에 동시에 들어가지 않음. `유선`/`무선` 태그도 여기서 파생
- **`경량` 태그** — 해당 sub_category 무게 범위 하위 35% 이내인 상품에만 부여 (1,271g 키보드에 "경량"이 붙는 문제 제거)
- **`와이드라스트` 태그** — `발볼넓음` 타겟 신발에만 부여
- **조사 자동 선택** — `description`의 `을/를`, `이/가`, `으로/로`를 앞 글자 받침에 따라 결정 (`apply_josa()`). 숫자로 끝나는 성분명도 처리 (예: `코엔자임Q10`)

---

## 5. 재생성 방법

세 스크립트 모두 **시드가 `20260811`로 고정**돼 있어 몇 번 실행해도 같은 데이터가 나옵니다.
의존성 없이 표준 라이브러리만 씁니다 (Python 3.12 확인).

```bash
cd c:/reviewSample
python generate_customers.py   # customers.csv
python generate_products.py    # products_*.csv 3개
python generate_purchases.py   # purchases.csv (위 4개 파일을 읽어서 생성)
```

**실행 순서가 중요합니다.** `generate_purchases.py`는 customers.csv와 products_*.csv를 읽어
FK와 속성 매칭을 맞추므로 반드시 마지막에 실행해야 합니다.

### 자주 건드릴 파라미터

| 위치 | 상수 | 기본값 | 설명 |
|---|---|---|---|
| generate_customers.py | `N_CUSTOMERS` | 300 | 고객 수 |
| generate_customers.py | `SKIN_TYPE_BY_AGE` 등 | — | 속성 상관관계 가중치. 균등하게 만들려면 값을 동일하게 |
| generate_products.py | `N_PER_CATEGORY` | 200 | 카테고리별 상품 수 |
| generate_purchases.py | `N_PURCHASES` | 1500 | 구매 건수 |
| generate_purchases.py | `EMPTY_REVIEW_RATE` | 0.04 | 빈 후기 비율. **0으로 두면 전부 후기 작성** |
| generate_purchases.py | `MAX_PER_CUSTOMER` | 15 | 고객당 최대 구매수 |
| generate_purchases.py | `RATING_WEIGHTS` | — | 매칭 여부별 별점 분포. 신호 세기 조절 |
| generate_purchases.py | `PRIMARY_CATEGORY_RATIO` | 0.70 | 주력 카테고리 집중도 |
| 공통 | `SEED` | 20260811 | 바꾸면 완전히 다른 데이터셋 |

---

## 6. 검증 결과

마지막 생성분 기준으로 아래 항목을 모두 확인했습니다.

**무결성**
- PK 유일성 — customer_id 300/300, product_id 600/600, purchase_id 1500/1500
- 결측 셀 0 (`review` 빈값 62건은 의도된 것)
- FK 오류 0건 — 모든 구매의 customer_id / product_id가 실재
- `purchases.category` ↔ 상품 테이블 `category` 100% 일치
- 전화번호 300개, 이메일 300개, 이름 300개 전부 유일

**논리 규칙**
- 가입일 이전 구매 0건, 미래 날짜(2026-08-11 초과) 0건
- is_holdout 정확히 300건 = 고객 300명 × 1건, 규칙 위반 0명
  (고객별 구매일을 서로 겹치지 않게 뽑아 "마지막 구매"가 동점 없이 확정됨)
- 상품의 `target_*` 값 집합이 customers의 대응 칼럼과 완전 일치 (`공용` 제외)

---

## 7. 참고파일과 달라진 점

| 항목 | portfolio_dummy_data.csv | 이 데이터셋 | 사유 |
|---|---|---|---|
| 카테고리 수 | 4개 | 3개 (`Home_Appliances` 제외) | 요구사항이 3개 카테고리 |
| Healthwear 범위 | 신발 + `트레이닝복` | **신발만** (`트레이닝복` → `워킹화`) | `user_trait`가 발 형태(평발/발볼넓음/칼발)뿐이라 의류가 섞이면 속성과 안 맞음 |
| customer_id 형식 | `C821` (3자리) | `C0001` (4자리) | 고객 300명 규모에 맞춤. 참고파일과 직접 조인하려면 3자리로 변경 필요 |
| 고객 속성 위치 | 구매 행의 `user_trait` | **고객 테이블의 3개 칼럼** | 속성은 고객의 성질이므로 정규화. 구매 테이블에서는 조인으로 획득 |
| 후기 다양성 | 카테고리당 4종 반복 | 1,028종 | 텍스트 분석 시 변별력 확보 |
| is_holdout | 전부 0 | 고객별 마지막 구매 = 300건 | Leave-One-Out 평가셋 |

---

## 8. 알려진 제약 / 다음에 할 수 있는 것

- **`sub_category`와 `user_trait`는 purchases에 없습니다.** product_id / customer_id로 조인하면 얻을 수 있어 중복 저장하지 않았습니다. 참고파일 형식과 완전히 맞추려면 두 칼럼을 비정규화해서 추가하면 됩니다.
- **A/B/C 카테고리 코드 칼럼이 없습니다.** `category`에 이름(`Cosmetics` 등)을 그대로 넣었습니다. 코드가 필요하면 매핑 칼럼 추가 가능.
- 반품·취소·재구매 여부, 결제 수단, 배송지 같은 칼럼은 없습니다.
- 구매 이력이 1건뿐인 고객이 있어, 그 고객은 holdout을 떼면 학습 데이터가 0건이 됩니다. 콜드스타트 테스트에는 오히려 유용하지만, 협업 필터링만 쓸 계획이면 최소 구매수를 2로 올리는 편이 낫습니다.
- 아직 SQLite 등 실제 DB 파일로는 묶지 않았습니다. CSV 5개가 전부입니다.
