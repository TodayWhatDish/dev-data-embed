LastUpdated : 2026=08-12

# DATAINFO.md — 반려견 추천용 더미 데이터 사전
`data/pet_customers.csv`, `pet_profiles.csv`, `pet_products.csv`, `pet_purchases.csv` 4개 파일의 컬럼과 값 의미를 정리합니다.
생성 스크립트는 `src/generate_pet_*.py` (모두 삭제 후 직접 재작성 중), 시드는 `20260812`로 고정돼 있어 재실행해도 같은 데이터가 나옵니다.

관계:

```
pet_customers (300)
    │ customer_id (PK)
    └──< pet_profiles (404)               # 고객 1명이 반려견 여러 마리 가능 (1:N)
              │ pet_id (PK)
              └──< pet_purchases (1,439)  # 반려견 1마리가 구매 여러 건 (1:N)
                        │ purchase_id (PK)
                        └──> pet_products (product_id FK, 200)
```

---

## 1. pet_customers.csv — 회원가입 정보

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `customer_id` | TEXT (PK) | `C0001` ~ `C0300` |
| `name` | TEXT | 한글 성명 |
| `phone` | TEXT | `010-XXXX-XXXX`, 유일값 |
| `email` | TEXT | 유일값 |
| `city` | TEXT | 거주 시/도. 17개 값(서울/경기/인천/부산/대구/광주/대전/울산/세종/강원/충북/충남/전북/전남/경북/경남/제주), 서울·경기 비중 높게 가중 |
| `account_type` | TEXT | `B2C`(일반 견주, 95%) / `B2B`(입점 업체, 5%) |
| `joined_at` | DATE | 2023-01-01 ~ 2026-08-11 |

*ㄱㄷ

---

## 2. pet_profiles.csv — 가입 후 입력하는 반려견 프로필

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `pet_id` | TEXT (PK) | `P0001` ~ (총 404건) |
| `customer_id` | TEXT (FK → pet_customers) | 고객 1명당 1~3마리(70%/25%/5% 확률) |
| `breed` | TEXT | 14개 견종 (말티즈/포메라니안/비숑프리제/푸들/시츄/치와와/웰시코기/시바견/진돗개/비글/코카스파니엘/골든리트리버/래브라도리트리버/보더콜리) |
| `age` | INTEGER | 0~15세 |
| `gender` | TEXT | `M` / `F` |
| `weight_kg` | REAL | 견종별 현실적 체중 범위에서 랜덤 (예: 말티즈 2~4kg, 골든리트리버 25~34kg) |
| `body_type` | TEXT | `마름` / `표준` / `비만` |
| `neutered` | INTEGER | 중성화여부. `0`=미중성화(35%) / `1`=중성화(65%) |
| `allergies` | TEXT | `없음`(과반) / `닭고기` / `소고기` / `유제품` / `곡물` 중 1개. **주의**: `pet_products.ingredients`와 정확히 같은 문자열일 때만 매칭됨 — `곡물`·`유제품`은 성분 목록에 동의어(예: 귀리·현미)로만 존재해서 문자열이 그대로 일치하지 않는 한 알러지 충돌로 안 잡힘 |
| `feeding_purpose` | TEXT | 급여목적. `없음` / `관절` / `다이어트` / `피부` |
| `diet_preference` | TEXT | 식성. `보통` / `식탐많음` / `식이까다로움` |
| `food_form_preference` | TEXT | 선호형태. `건식` / `습식` / `혼합`(둘 다 허용 취급) |
| `budget` | INTEGER | 10,000 / 20,000 / 30,000 / 50,000 / 80,000 / 120,000원 중 1개 |
| `place_type_preference` | TEXT | 선호 장소유형. `카페` / `공원` / `음식점` / `병원` / `펜션` (명소 데이터는 아직 없어서 현재는 참고용) |
| `updated_at` | DATE | 프로필 최종 수정일 (더미 데이터는 전부 2026-08-11로 통일) |

---

## 3. pet_products.csv — 사료/간식 상품 마스터

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `product_id` | TEXT (PK) | `F0001` ~ `F0200` (사료 100개 + 간식 100개) |
| `category` | TEXT | `사료` / `간식` |
| `sub_category` | TEXT | 사료: `건식사료`/`습식사료`/`실버사료`/`퍼피사료`, 간식: `수제간식`/`트릿`/`덴탈껌`/`동결건조간식` |
| `brand` | TEXT | 가상 브랜드명 10종 (멍푸드/펫키친/바크앤조이/네이처독/도그밀/헬시포/퍼피랩/와일드포/스노우독/그레인프리랩) |
| `product_name` | TEXT | `{브랜드} {sub_category}` — 번호가 없어 200개 중 125개가 동명이품. 상품 식별은 `product_id` 로 한다 |
| `price` | INTEGER | 사료 15,000~89,000원, 간식 2,900~25,000원 |
| `weight_g` | INTEGER | 사료 400~5,000g, 간식 50~500g |
| `target_feeding_purpose` | TEXT | `관절`/`다이어트`/`피부`(특정 목적 겨냥, 70%) 또는 `공용`(30%) — `pet_profiles.feeding_purpose`와 같은 값 체계 |
| `target_food_form` | TEXT | `건식`/`습식`(80%) 또는 `공용`(20%) — `pet_profiles.food_form_preference`와 같은 값 체계 |
| `ingredients` | TEXT | `\|` 구분 다중값. 14종 성분 풀에서 2~4개 랜덤 조합 (닭고기/소고기/연어/오리/고구마/단호박/스피루리나/글루코사민/프로바이오틱스/오메가3/유산균/홍합추출물/귀리/현미) |
| `tags` | TEXT | `\|` 구분. `sub_category` + (공용이 아니면 `target_feeding_purpose`) + `ingredients` 전체 + `target_food_form` |
| `description` | TEXT | `"{sub_category} 제품으로 {성분1}/{성분2} 성분을 담았습니다."` 형태 자동 생성 문장 |

---

## 4. pet_purchases.csv — 구매/후기 이력

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `purchase_id` | TEXT (PK) | `O00001` ~ (총 1,439건) |
| `customer_id` | TEXT (FK → pet_customers) | |
| `pet_id` | TEXT (FK → pet_profiles) | 이 구매가 어느 반려견 기준인지 |
| `product_id` | TEXT (FK → pet_products) | |
| `category` | TEXT | `사료`(60%) / `간식`(40%) — 해당 구매의 상품 카테고리 |
| `purchased_at` | DATE | 반려견 소속 고객의 `joined_at` 이후 ~ 2026-08-11 사이, 반려견당 오름차순 정렬 |
| `quantity` | INTEGER | 1(74%) / 2(15%) / 3(8%) / 5(3%) |
| `rating` | INTEGER | 1~5점. **핵심 신호** — 아래 4.1 참고 |
| `review` | TEXT | 별점 구간별 문장 템플릿 3~4종 중 1개, 4% 확률로 빈 문자열 |
| `is_holdout` | INTEGER | 반려견별 **가장 최근 구매 1건**만 `1`, 나머지 `0` — 추천 로직 검증(leave-one-out)용 |

### 4.1 rating에 심어둔 신호 (추천 로직의 핵심 재료)

`pet_profiles`와 `pet_products`의 속성 매칭 여부에 따라 별점 분포가 달라지도록 설계했습니다.

| 조건 | 별점 분포 경향 |
|---|---|
| 알러지 충돌 (`allergies`가 `ingredients`에 그대로 존재) | 1~2점 쏠림 (실측 평균 1.82) |
| `feeding_purpose` + `food_form_preference` 완전 매칭(또는 공용) | 4~5점 쏠림 (실측 평균 4.48) |
| 둘 중 하나만 매칭 | 중간 (3~4점대) |
| 매칭 없음 | 3점대 (실측 평균 3.78) |

즉, 별점을 독립적인 랜덤값으로 취급하면 안 되고 **"이 반려견 조건에 이 상품이 얼마나 맞았는가"의 결과물**로 봐야 합니다. 스코어링 로직(③ 추천 결과 산출) 짤 때 이 규칙을 그대로 재현하면 됩니다.
