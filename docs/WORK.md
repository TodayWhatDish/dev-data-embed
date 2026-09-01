## 작업일지
## 2026-08-12
## 작업일지
> 화장품 도메인으로 되어 있던 임베딩 파이프라인을 애견 도메인으로 전환.
> 코드 상세는 `src/src.md` 참고.

## 2026-08-25

### C블록을 최소 형태로 확정했다 — 넣었던 컬럼을 대부분 도로 뺐다

하루 동안 `purchases`/`reviews` 에 컬럼을 여러 개 넣었다가 뺐다. 최종은 이거다.

    purchases  purchase_id, pet_id, product_id, purchased_at, quantity, unit_price_krw
    reviews    purchase_id, rating, body, is_holdout, reviewed_at

전부 NOT NULL. `purchases` 는 append-only(UPDATE 없음), `reviews` 는 `is_holdout` 만 UPDATE 된다.

뺀 것과 **다시 넣게 되는 조건**을 남긴다. 근거 없이 다시 논쟁하지 않으려고 쓴다.

| 뺀 것 | 왜 | 다시 넣을 때 |
|---|---|---|
| `size_at_purchase` / `age_month_at_purchase` | 반정규화인데 **측정을 안 했다** | 조인 비용·드리프트를 재고 나서. `docu.md` §3 |
| `weight_kg` / `neutered` 스냅샷 | `products` 에 대응 필터가 없다 | 체중대별·중성화별 후기 비교를 하기로 할 때 |
| `pet_allergies.recorded_at` | 알러지를 **배제 전용**으로 좁혔다 | 후기 코호트(`GOAL.md` 128행)를 살릴 때 |
| `reviews.allergy_reaction` | 층이 틀렸다(아래) | 원인 원료를 지목하는 구조라면 |
| `purchases.created_at` | UPDATE 가 없으니 `purchased_at` 과 같은 값 | 환불을 다루면 `refunded_at`(플래그 아님) |
| `reviews.created_at` / `updated_at` | 후기 수정·삭제 기능을 안 넣기로 | 실험 재현이 필요해지면 D블록에서 |

**관통하는 규칙 하나 — 소비자 없는 컬럼은 두지 않는다.** 스냅샷을 고를 때도 같은 기준이었다:
`products` 의 필터 컬럼(`target_size_*`, `target_age_*`)에 직접 물리느냐. 그래서 `weight_kg` 과
`neutered` 가 먼저 떨어졌고, 결국 측정 없이는 나머지 둘도 안 넣기로 했다.

### `allergy_reaction` 은 층이 틀린 컬럼이었다

"이 제품 먹고 반응이 났다"는 결국 **이 아이에게 알러지가 있다**는 사실이다. 그러면 갈 자리는
후기가 아니라 `pet_allergies` 고, 거기 들어가야 `v_product_safety` 가 다음부터 그 원료를 배제한다.
후기에 0/1 로 적어두면 기록만 남고 아무도 보호받지 못한다.
한 제품에 유발 원료가 여럿이면 0/1 로 지목도 못 하는데, 보호자는 애초에 원인 원료를 모른다.

신호는 `body` 에서 읽는다 — `GOAL.md` 121행이 "리뷰 텍스트 속에서 알레르기 반응을 읽어내어"를
D블록 임베딩의 일로 이미 정해뒀다. 체크박스가 그 설계와 중복이었다.

### 인덱스를 안 늘렸다 (실측)

`purchases.purchased_at` 단독 인덱스와 `reviews(reviewed_at)` 부분 인덱스를 검토하고 둘 다 뺐다.

`purchased_at` 은 `idx_purchases_pet(pet_id, purchased_at)` /
`idx_purchases_product(product_id, purchased_at)` 의 두 번째 컬럼이라 정렬까지 처리된다
(`ORDER BY purchased_at DESC` 에 temp b-tree 가 안 붙는다). 못 타는 건 "전체 최근순"뿐인데
추천 경로가 전부 `pet_id`/`product_id` 에서 출발해서 그런 쿼리가 없다.

임베딩 배치용 `reviews(reviewed_at) WHERE is_holdout = 0` 은 후기 20만 건으로 재봤다.
**선택도가 갈림길이었다:**

    최근 1개월  22,418행 (11.2%)   스캔 24.18 ms   인덱스 52.84 ms   <- 인덱스가 2배 느리다
    최근 1개월   9,238행 ( 4.6%)   스캔 42.06 ms   인덱스 35.48 ms
    최근 2주     5,110행 ( 2.6%)   스캔 39.75 ms   인덱스 20.52 ms
    최근 1일     1,872행 ( 0.9%)   스캔 35.56 ms   인덱스  7.17 ms

10% 넘게 뽑으면 인덱스가 진다 — 행 위치를 찾아도 `body` 를 읽으러 테이블 페이지를 건건이
뒤져야 하는데, 그럴 바엔 순차로 다 읽는 게 싸다. 5% 아래면 이기지만 42→35ms 라
임베딩 배치에서는 모델 인코딩 수십 초에 묻히는 차이다.

**임베딩 주기·윈도우도 지금은 정하지 않는다.** 슬라이딩 윈도우(오래된 후기 버림)와
누적+증분 둘 다 검토했는데, `review_embeddings` 를 `purchase_id` PK + BLOB 으로 잡으면
`INSERT OR REPLACE` 하나로 어느 쪽이든 되므로 지금 정할 필요가 없다.
현재 `embed.py` 는 매번 `DROP TABLE` 후 전량 재계산이고 이 규모에선 그걸로 충분하다.

**검증** — 18 테이블 + 2 뷰 + 14 인덱스. `check_fk_targets()` 통과.
되돌린 컬럼들은 코드·문서 양쪽에 잔재가 없는지 grep 으로 확인했다.

## 2026-08-24 (2)

### 삭제 사슬을 끊었다 — CASCADE -> RESTRICT, 그리고 구매 시점 스냅샷

C블록(`purchase_schema`)을 붙이니 삭제 사슬이 4단이 됐다. 실측으로 확인:

    삭제 전:         {'users': 1, 'pets': 1, 'purchases': 1, 'reviews': 1}
    users DELETE 후: {'users': 0, 'pets': 0, 'purchases': 0, 'reviews': 0}

`DELETE FROM users` 한 줄이 후기까지 지운다. `docu.md` §1 이 "탈퇴는 DELETE 가 아니다"라고
적어만 뒀지 DB 는 아무것도 막지 않고 있었다.

**바꾼 것** — `pets.user_id`, `purchases.pet_id` 를 CASCADE -> RESTRICT.

    users 삭제   -> 차단: FOREIGN KEY constraint failed
    pets 삭제    -> 차단: FOREIGN KEY constraint failed
    products삭제 -> 차단: FOREIGN KEY constraint failed
    구매 삭제    -> 후기도 같이: 0 행   (이 경로만 CASCADE 로 남김)

`products` 가 이미 RESTRICT 였으므로 패턴이 같아졌다 — **이력이 달린 마스터 행은 못 지운다.**
`reviews.purchase_id` 만 CASCADE 로 뒀다. 구매 오등록을 정정하면 그 후기는 근거를 잃는다.

`pet_breeds`/`pet_allergies` 는 CASCADE 유지다. 그건 이력이 아니라 pet 의 속성이라
pet 이 사라지면 같이 사라지는 게 맞다.

**대가.** GDPR 삭제권 행사는 이제 `reviews` -> `purchases` -> `pets` -> `users` 순서로
직접 지워야 한다. 한 줄로 안 된다. 그게 안전장치다 — 되돌릴 수 없는 작업이 한 줄이면 안 된다.

### `purchases` 에 체중·나이 스냅샷 추가

    weight_kg_at_purchase  REAL    CHECK (> 0)     -- NULL 허용
    age_month_at_purchase  INTEGER CHECK (>= 0)    -- NULL 허용

**개인정보와 무관하게 이미 있던 버그를 고친다.** `pets.weight_kg` 는 시간이 지나면 바뀐다.
후기를 읽을 때 `pets` 를 조인하면 **지금** 값이 나오므로, 3년 전 소형견 시절에 쓴 후기가
오늘 대형견 후기로 해석된다. 세그먼트 추천이 에러 없이 조용히 틀려진다.

같은 테이블의 `unit_price_krw` 가 이미 같은 원칙이다 — 그때 얼마였는지는 사실이지 파생값이 아니다.
체중도 같다. 규칙 3(사실 저장, 상태 파생)의 예외가 아니라 같은 규칙의 적용이다:
파생의 기준점이 "지금"이 아니라 "구매 시점"인데 그 시점은 이 행에만 있다.

`size` 는 넣지 않았다. `weight_kg` 에서 나오고, 1~5 척도가 바뀌면 다시 계산할 수 있어야 한다.
체구 구간은 앱의 판단이지 사실이 아니다.

**검증** — 18 테이블 + 2 뷰 + 14 인덱스. `check_fk_targets()` 통과.
RESTRICT 3종 차단과 `reviews` CASCADE 를 임시 DB 에서 직접 확인했다(위 출력).

## 2026-08-26

### 조인하면 앞뒤가 안 맞던 값 166건 + 100g당 가격 파생을 고쳤다

행 하나만 보면 멀쩡한데 **두 값을 같이 보면 틀린** 것들이다. FK 도 CHECK 도 STRICT 도
못 잡는 자리라, 나중에 조인해서 쓸 때가 되어서야 드러난다.

| 모순 | 건수 | 원인 |
|---|---|---|
| `products`: 수정일 < 등록일 | **103** | 두 값을 서로 안 보고 각각 뽑았다 |
| `pets`: 태어나기 전에 등록됨 | **45** | 하한을 주인 가입일만 봤다. 생일도 하한이다 |
| `users`: 탈퇴한 뒤에 로그인 | **7** | `withdrawn_at` 을 `last_login_at` 과 무관하게 뽑았다 |
| 같은 날짜인데 시각만 역전 | **10** | 날짜를 뽑고 시:분:초를 나중에 무작위로 붙였다 |
| 파생 (태어나기 전 활동종료 등) | **1** | 위의 결과 |

**시각 역전이 구조적 원인이었다.** `rdate()` 로 날짜를 뽑고 `dt()` 가 시:분:초를 따로
무작위로 붙이는 구조라, 시작과 끝이 같은 날이면 `09:00` 가입 → `03:00` 로그인이 나온다.
초 단위로 뽑는 `rdt(start, end)` 를 만들어 대체했다. 날짜 경계가 사라지니 구멍도 사라진다.

**나머지는 전부 "뒤에 오는 사건은 앞선 사건을 하한으로 삼는다"로 정리된다.**

```
users    : 가입 → 로그인 → 탈퇴 → 수정
pets     : max(생일, 주인 가입) → 등록 → 활동종료 → 수정
products : 등록 → 수정
```

`pets` 의 하한이 **두 개**인 게 놓치기 쉬웠다. 주인 가입일만 보면 2023년에 가입한 사람이
2025년에 태어날 강아지를 2023년에 등록한 행이 만들어진다.

### 100g당 가격 — 중량에서 파생시켰다

`schema/README.md` 가 "100g당 가격은 `price_krw` / `weight_g` 에서 나온다"고 파생값으로
못박아뒀는데, 가격과 중량을 독립적으로 뽑고 있어서 **46배**까지 벌어졌다
(500g 81,000원 = 100g당 16,200원 / 4.7kg 16,900원 = 100g당 360원).
파생값이 무의미하면 그 컬럼 설계 자체가 헛돈다.

**중량을 먼저 뽑고 제형별 100g당 단가를 곱하는 방식으로 바꿨다.** 대용량일수록 단가가
떨어지는 계수도 넣었다.

| 제형 | 100g당 중앙 | 중량 범위 |
|---|---|---|
| 건식 | 738원 | 60g ~ 14.9kg |
| 습식 | 2,079원 | 60g ~ 2.0kg |
| 생식 | 2,867원 | 230g ~ 2.0kg |
| 동결건조 | 9,412원 | 30g ~ 1.1kg |

제형 **안에서의** 편차는 1.6~3.6배로 좁혀졌고, 제형 **사이** 차이는 실제 시장과 같은 방향이다.
대용량 할인도 확인된다 — 건식 사료 7kg↑ 100g당 610원 / 1~3kg 958원.

**검증** — 시간 역전 14종 전부 0건, 미래 시각 0건, FK 위반 0건.
`v_product_safety` Safe 33,920 / None 11,862 / WARN 5,477.
어제 채운 문서 요구 케이스 6종(복합 원료·`min==max`·중복 phone 등)도 전부 유지된다.

`data/README.md` 에 **"조인했을 때 앞뒤가 맞는가"** 절을 새로 만들어 위 순서 규칙을 적었다.

### 적재 순서를 손으로 적던 것을 FK 그래프에서 계산하게 바꿨다

`load_csv.py` 의 `ORDER` 는 내가 DDL 을 눈으로 보고 옮겨 적은 목록이었다. 값은 맞았지만
**정답이 이미 DDL 안에 있는데 사람이 베껴 적는 구조**라, 테이블이 하나 늘면 사람이
끼워 넣어야 하고 위치를 틀리면 `IntegrityError` 로 터진다. `execute_schema.drop_all()` 이
DROP 목록을 모듈에 두지 않는 것과 같은 문제다 — 목록과 실제가 어긋나면 조용히 틀린다.

**`PRAGMA foreign_key_list` 로 그래프를 뽑아 위상 정렬한다** (`resolve_order()`).
실행할 때마다 계산하고 근거를 같이 출력한다.

```
 1. allergens                     [자기참조]
 4. products                       (시드 참조: product_categories)
 7. pets                          <- users
13. pet_breeds                    <- breeds, pets
```

**순서가 두 층이라는 게 핵심이었다.**

| 층 | 문제 | 함수 |
|---|---|---|
| 테이블 사이 | `users` 가 `pets` 보다 먼저 | `resolve_order()` |
| 한 테이블 안 | `allergens` 의 부모 **행**이 먼저 | `order_rows_parents_first()` |

자기참조(`allergens.parent_id -> allergens`)를 테이블 그래프에 넣으면 자기 자신을 기다리느라
정렬이 멈춘다. 그래서 테이블 레벨에서 빼고 행 레벨에서 푼다. **둘은 같은 문제**라
`topo_sort()` 하나를 양쪽에서 쓴다 — 코드를 두 벌 두면 한쪽만 고치는 날이 온다.

적재 대상이 아닌 부모(코드 SEEDS 로 이미 채워진 `animal_categories` 등)는 조건에서 뺀다.
이미 있는 것을 기다릴 이유가 없다.

**깨뜨려서 확인한 것 6가지**

| 테스트 | 결과 |
|---|---|
| 테이블 순환 FK (a→b→c→a) | `RuntimeError` 로 정지 |
| 적재 대상 밖의 부모를 참조 | 무시하고 통과 (의도) |
| C블록 2테이블 추가 | 코드 수정 없이 14·15번에 자동 배치 |
| `allergens.csv` 행 순서 섞기 | 정상 적재 |
| `allergens` 에 순환 넣기(행 레벨) | `RuntimeError` 로 정지 |
| CSV 헤더 오타 | `ValueError` 로 정지 |

세 번째가 이 작업의 목적이다. `SOURCES` 에 파일만 추가하면 순서는 다시 계산된다.

### schema/ 4개 문서를 전수 대조해 모순 4가지를 더 잡았다

컬럼 값은 각각 유효한데 **여러 행을 같이 보면 앞뒤가 안 맞는** 것들이었다.
FK 도 CHECK 도 못 잡는 자리라 조인해서 쓸 때가 되어서야 드러난다.

**① 로그인한 적 없는 유저가 펫을 등록했다 — 14명 전원**

`last_login_at` 이 NULL 이면 앱에 들어온 적이 없다는 뜻인데, 그 14명이 전부 펫을 갖고 있었다.
더 넓게는 **마지막 로그인 이후에 찍힌 펫 등록·수정이 96건**이었다. `last_login_at` 은
'마지막' 로그인이므로 정의상 그 뒤의 앱 활동은 없다.

펫 등록은 로그인해야 하는 일이라는 것을 생성 규칙으로 넣었다.

```
last_login_at 이 NULL      -> 펫 0마리
펫 등록·수정·활동종료 시각    <= min(마지막 로그인, 탈퇴 시각)
마지막 로그인 뒤에 태어난 아이 -> 그 유저에게 붙지 않는다(나이를 구간에 맞춰 올린다)
```

마지막 줄이 부수 효과로 **휴면 유저에게 갓난 강아지가 붙는 것**도 막는다.

**② 알러지를 골라도 배제되는 제품이 0개 — 72마리**

`allergens` 에는 있는데 그걸 가리키는 `ingredients` 가 하나도 없는 **리프**가 9개였다.

```
게 · 땅콩 · 호밀 · 수수 · 곤충단백 · 인공색소 · 인공보존료 · 도라지 · 더덕
```

`땅콩 알러지`를 등록해도 걸러지는 제품이 없으면 **하드 필터가 조용히 무의미해진다.**
앞 7종은 실제 사료·간식에 흔한데 원료 목록에서 빠져 있었다 — 원료 7종과 매핑 7건을 추가했다
(`ingredients` 50→57, `ingredient_allergens` 49→56). 첨가물(착색료·소르빈산칼륨)은
간식 35% / 사료 10% 확률로 들어가게 했다.

`도라지`·`더덕` 둘은 그대로 뒀다. 한방 간식에만 쓰여 현재 취급 제품에 없는 게 자연스럽고,
'마스터에는 있지만 아무 제품에도 안 들어가는 알러지원'이라는 상태도 하나쯤 있어야 한다.
중간 노드 15개(육류·가금류 등)가 원료를 직접 안 가리키는 것은 정상이다 — 자식이 가리킨다.

**③ 한 집에 같은 이름 펫 두 마리 — 5쌍.** 이름 풀이 40개뿐이라 겹쳤다. 유저 안에서 비복원으로 바꿨다.

**④ 펫이 0마리인 유저가 한 명도 없었다.** 300명 전원이 펫을 갖고 있었다.
가입만 하고 아직 안 올린 유저 6% 를 넣어 25명이 됐다. **이 상태가 없으면 앱이 그걸 어떻게
다루는지 시험할 수 없다** — 다른 0행 케이스들과 같은 이유다.

**같이 확인해서 이상 없던 것** — `breeds` 에 '믹스'/'모름' 행 없음, 제품이 3단계 분류를
가리키지 않음, 사료에 소분류 없음, `products.name` 중복 없음, `(auth_provider, auth_uid)` 쌍 중복 없음,
`pet_allergies` 에 중간 노드만 있고 자식이 빠진 경우 없음.

**검증** — 시간 순서 8종 + 값 정합성 9종 전부 0건. FK 위반 0건.
`v_product_safety` Safe 32,446 / None 7,492 / WARN 4,438.
문서 요구 케이스 12종 전부 유지.

### 품종 분포를 고쳤다 — 코숏이 아비시니안만큼만 나오던 것

**① 고양이 품종이 균등 분포였다.** `rng.sample()` 로 13종에서 그냥 뽑아서
코리안숏헤어(8)가 브리티시숏헤어(12)보다 적게 나왔다. 국내 반려묘 구성으로는 말이 안 된다.
`BREED_WEIGHT` 를 넣고 비복원 가중 추출로 바꿨다(`pick_breeds()`).

| | 이전 | 지금 |
|---|---|---|
| 코리안숏헤어 | 8 | **41** |
| 스코티시폴드 | 7 | 9 |
| 브리티시숏헤어 | **12** | 5 |
| 노르웨이숲 | 10 | 2 |

**개는 균등으로 둔다.** 근거로 쓸 자료가 없다 — 임의 가중치를 넣느니 균등인 편이 낫다.

**벵갈·아비시니안·터키시앙고라는 등록된 펫이 0마리가 됐다.** 가중치가 낮은데 고양이가
83마리뿐이라 그렇다. 버그가 아니다 — `breeds` 는 선택지 목록이고, 아무도 안 키우는 품종이
목록에 있는 것은 정상이다.

**② 품종 0행 10% 에 근거가 없었다.** 축종별로 나눴다.

```
개     8%   유기견 입양·시골 잡종
고양이  4%   '코숏'이라는 포괄 명칭이 있어 '모름'이 드물다 —
            길에서 온 아이도 보호자는 코숏이라고 적는다
```

같은 이유로 고양이 믹스 비율도 개보다 낮췄다(개 22% / 고양이 10%). 전체 0행은 7.2% 가 됐다.
**0 으로는 만들지 않는다** — `pet_schema.md` 가 0행 = 품종 모름으로 정의했고,
없으면 그 상태가 데이터에 존재하지 않게 된다.

### 옛 `data/pet_*.csv` 는 더 이상 참고하지 않는다

지금까지 시/도 비중(서울 97 / 경기 58 …)과 고객당 반려동물 수(213/70/17)를 옛 CSV 실측에서
가져오고 있었는데, 그 파일들을 참고 대상에서 뺐다. 견종 가중치도 거기서 가져오려다 접었다.

**이미 들어간 두 값(`REGIONS`, 펫 수 분포)은 그대로 뒀다** — 값 자체가 틀린 게 아니라
출처가 없어졌을 뿐이고, 지금 바꾸면 근거 없는 다른 숫자로 갈아끼우는 셈이다.
바꿀 일이 생기면 그때 도메인 상식으로 다시 정한다.

**검증** — 시간 역전 7종 + 속성 정합성 7종 전부 0건. 중복 품종 등록 0건
(가중 추출을 비복원으로 만든 이유). FK 위반 0건.
`v_product_safety` Safe 34,321 / None 9,767 / WARN 5,217.

### `product_nutrition` 결측이 분류를 안 보던 것을 고쳤다

성분표 유무를 분류와 무관하게 일괄 85% 로 정하고 있었다. 그래서 **사료 113개 중 14개가
성분표 없이** 나왔는데, 사료관리법상 배합사료는 등록성분량(조단백·조지방·조섬유·조회분 등)
표시가 **의무**라 그런 사료는 유통될 수 없다. `product_schema.md` 도 결측의 방향을 적어뒀다 —
"**사료는** 성분표가 있고 **간식은** 없는 경우가 흔하다."

분류별 확률(`NUTRITION_RATE`)로 바꿨다.

| 분류 | 이전 | 지금 |
|---|---|---|
| 사료 | 12.4% (14/113) | **0.9%** (1/108) |
| 덴탈껌 | 40.6% | 38.5% |
| 수제간식 | 12.9% | 45.5% |
| 트릿 | 22.2% | 20.0% |

**결측 자체는 남겼다.** 31/200 이 여전히 성분표가 없다 — 그게 이 표를 `products` 에서
분리한 이유이므로 0 으로 만들면 안 된다. 쏠리는 방향만 바로잡았다.

**드러난 잠복 결함 하나를 같이 고쳤다.** 사료 쪽 성분표가 늘자 **보증성분 합계가 100% 를
넘는 행**이 나왔다. 습식은 수분을 70~82% 로 뽑는데 나머지 4개를 더하면 최대 104.5% 가 된다.
5개 합이 99% 를 넘지 않도록 수분에 상한을 걸었다(나머지 1% 는 탄수화물 몫).
이전 데이터에서 안 보였던 건 그 제품이 마침 성분표 없는 쪽에 걸려 있었기 때문이다.

**검증** — 시간 역전 7종 + 속성 정합성 6종 전부 0건. FK 위반 0건.
`v_product_safety` Safe 34,235 / None 10,158 / WARN 5,581.
문서 요구 케이스 6종도 전부 유지된다.

**남겨둔 것 2가지** (오늘 범위 밖)

- **고양이 품종이 균등 분포다.** 코리안숏헤어가 브리티시숏헤어보다 적게 나온다. 견종은 옛
  `pet_profiles.csv` 실측 분포를 참고했지만 고양이는 참고할 옛 데이터가 없어 13종에서 균등하게
  뽑고 있다. 한국 반려묘 구성으로는 코숏이 압도적이어야 한다.
- **품종 0행 비율 10% 에 근거가 없다.** 0행이 존재해야 하는 것 자체는 맞다
  (`pet_schema.md` 가 0행 = 품종 모름으로 정의했고, 없으면 그 상태가 시험되지 않는다).
  다만 10% 라는 수치는 실제 통계가 아니라 임의로 정한 값이다. 옛 CSV 는 404행 전부 품종이 있었다.

### 스키마 문서가 요구한 케이스가 데이터에 없던 것 6가지를 채웠다

어제 CSV 를 만들 때 `docu/schema/product_schema.md`(26KB, 4개 중 가장 크다)를 **안 읽고**
`product_schema.py` 의 DDL 만 보고 만들었다. 컬럼 정의는 코드에 다 있지만 **설계 노트의 "왜"는
문서에만 있고**, 그 "왜"가 곧 "이런 경우가 있으니 이 구조여야 한다"라서 데이터에 그 경우를
넣을 생각을 못 했다. 4개 문서를 전부 다시 읽고 대조한 결과다.

| 문서가 말한 것 | 어제 | 오늘 |
|---|---|---|
| 복합 원료는 알러지원을 여러 개 갖는다(`'베이커리 부산물'`=밀·계란·유제품) | **0종** | 5종 |
| 소형견 전용 = `target_size_min 2, max 2` | **0개** | 17개 |
| `description` 은 콜드스타트 임베딩 대상 | 상투 문구 | 축종·체구·연령·주원료·목적 |
| 같은 uid 라도 제공자가 다르면 다른 계정 | **0쌍** | 16쌍 |
| `phone` 은 실제로 유일하지 않다(가족 공유) | 중복 **0** | 11개 |
| `allergens.name_eng` 는 없으면 NULL | NULL **0** | 2행(도라지·더덕) |

**복합 원료가 이 중 제일 컸다.** `ingredient_allergens` 가 컬럼 하나가 아니라 다대다 테이블인
유일한 이유가 "복합 원료는 알러지원을 여러 개 갖는다"인데, 전부 1:1 매핑이면 컬럼 하나로 둔
설계와 결과가 같다. 즉 **다대다를 고른 판단이 데이터로 한 번도 시험되지 않는 상태**였다.
지금은 복합 원료 때문에 위험 판정된 쌍이 1,193개다 — 컬럼 하나였다면 그중 상당수가
조용히 `Safe` 로 통과했을 자리다.

이건 어제 다른 테이블에서는 잡은 실수와 같은 종류다. "전부 `ingredients_verified = 1` 이면
`None` 분기가 한 번도 안 나온다"는 잡아서 22% 를 `0` 으로 남겼는데, "전부 1:1 매핑이면
다대다가 무의미하다"는 못 잡았다. 차이는 문서를 읽었느냐 하나뿐이다.

**같이 한 것**

- `data/master/` 3종 갱신 — `ingredients` 45→50(복합 원료 5종), `ingredient_allergens` 35→49,
  `allergens` 47→49(표준 영문명이 없는 도라지·더덕).
- `data/README.md` 에 **"문서가 요구한 케이스를 데이터가 담고 있는가"** 절을 새로 만들었다.
  이번에 놓친 원인이 그 점검표가 없었던 것이라, 스키마 문서를 고칠 때 같이 보도록 남긴다.

**검증** — `PRAGMA foreign_key_check` 0건. `v_product_safety` Safe 36,012 / None 9,236 / WARN 4,554.
활성 펫 399마리 중 Safe 후보 0개가 4마리인데 넷 다 `단백질` 최상위를 골라 육류·어류·갑각류·
유제품·난류가 통째로 배제된 개체다(알러지 25~26행). 버그가 아니고, 이때 앱이 무엇을 보여줄지는
여전히 안 정했다.

**하나 남겨둔다** — `price_krw` 와 `weight_g` 를 서로 독립적으로 뽑고 있어서 100g당 가격이
360원~16,200원으로 45배 벌어진다. `schema/README.md` 가 "100g당 가격은 `price_krw` / `weight_g`
에서 나온다"고 파생값으로 못박아둔 것과 어긋난다. 고치려면 중량을 먼저 정하고 제형별 단가를
곱하면 된다. 이번 범위(문서가 요구한 케이스 채우기) 밖이라 손대지 않았다.

## 2026-08-25

### 16테이블 스키마용 CSV 파이프라인 — `data/master` + `data/seed` 로 갈랐다

옛 `data/pet_*.csv` 4종은 옛 4테이블 비정규화 스키마의 것이라 새 스키마에 못 넣는다
(`C0001` TEXT ID / `age` 정수 / `body_type='마름'` / `ingredients` 파이프 다중값).
새로 만들되, 값 분포는 그 파일들에서 실측해 옮겼다.

**CSV 를 세 갈래로 나눴다.** 재생성 비용이 서로 달라서다.

| 갈래 | 테이블 | 재생성 |
|---|---|---|
| 코드 `SEEDS` | `animal_categories`, `product_categories`, `feeding_purposes` | 스키마와 함께 |
| `data/master/` | `allergens`(47), `breeds`(36), `ingredients`(45), `ingredient_allergens`(35) | **하지 않는다** |
| `data/seed/` | 나머지 9테이블 (3,279행) | 언제든 |

마스터를 재생성하지 않는 것이 이 구분의 이유다. `allergen_id` 가 한 번 바뀌면 손으로 넣은
`ingredient_allergens` 매핑이 **에러 없이** 어긋난다. 생성기는 마스터를 읽기만 한다.
코드 `SEEDS` 에 이미 있는 3개를 CSV 로 또 빼지 않은 것도 같은 이유(같은 값이 두 군데)다.

**추가한 것**

- `src/make_data/gen_seed.py` — 시드 `20260812` 고정, 데이터의 '오늘'도 `2026-08-25` 로 고정.
  `date.today()` 를 쓰면 재실행마다 나이·휴면 판정이 흔들려 벤치를 비교할 수 없다.
- `src/load_csv.py` — 옛 `load_db.py` 를 대체한다. DDL 을 만들지 않는다(스키마의 단일 원천은
  `src/create_schema/`). 값 캐스팅도 하지 않는다 — STRICT 가 이미 하는 일이다(설계규칙 7번).
- `data/README.md` — CSV 규약과 위 3분할의 근거.

**DB 가 못 막는 것을 생성기가 맡았다.** `docu/schema/` 가 "앱이 막는다"로 적어둔 것들이다.

- `pet_allergies` 펼침 — 카테고리를 고르면 하위 전부 + 고른 카테고리 행.
- 축종 정합성 — 개 `pet` 에 고양이 `breed` 를 붙여도 FK 는 통과한다. 실측 위반 0건.
- 판정 3분법이 관측되도록 `ingredients_verified = 0` 제품 42개와
  `product_animal_categories` 0행 제품 6개를 일부러 남겼다. 전부 채우면 `None` 분기가
  한 번도 안 나와서 스키마는 멀쩡한데 검증만 헛돈다.

**검증**

- `PRAGMA foreign_key_check` 0건. `v_product_safety` 전체 Safe 34,526 / None 8,724 / WARN 4,276.
- 활성 펫 383마리 중 Safe 후보 0개가 3마리. 버그가 아니다 — 2마리는 `단백질` 최상위를 골랐고,
  1마리는 `육류`+`새우` 알러지 고양이인데 고양이 후보 51개가 전부 육류를 쓴다.
  **이 경우 앱이 무엇을 보여줄지는 아직 안 정했다.**
- 로더 방어 2종을 실제로 깨뜨려 확인했다 — `allergens.csv` 행 순서를 섞어도 적재 성공
  (`parent_id` 보고 부모부터 정렬), `pets.csv` 헤더에 오타를 넣으면 `ValueError` 로 정지.
- `gen_seed.py` 재실행 시 9개 파일 md5 동일. 전 파일 UTF-8 no-BOM / LF.

**고친 데이터 결함 하나** — 체중을 품종 표준 범위에서만 뽑아서 '생후 5개월 시바견 11.1kg'
같은 행이 나왔다. 12개월 미만은 월령에 비례해 깎는다. 급여량·칼로리 계산의 기준이 되는
값이라 그대로 두면 조용히 틀린 근거가 된다.

**아직 없는 것** — 구매·리뷰(C블록)가 새 스키마로 포팅되지 않아 옛 `pet_purchases.csv`
(1,439건, 별점에 매칭 신호가 심긴 것)에 해당하는 CSV 는 못 만든다. `src/embed.py` 도
그때까지 옛 `pet_reco.db` 경로다.

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

`user.db` 재생성, `load_db.py` 재작성, 더미 CSV 재생성, `embed.py` 포팅.
상세는 `local/ToDo.md` §9.

## query.py

질문/체급/알레르기를 입력받아 프로필 조건으로 거른 벡터검색 결과를 보여주고 매 질문을 query_log.jsonl에 기록

### 남은 과제

- **더미데이터 불일치**: `건식사료` 상품인데 `target_food_form`이 `습식`이거나,
  `중형견 비글` 리뷰 본문에 "소형견이라..."가 들어있는 행이 있다.
  RAG 근거로 쓰면 LLM이 모순된 답을 만든다. 데이터 생성 로직 점검 필요.
  → **2026-08-17 해소** (아래 2026-08-17 §5 참고).
- **토큰 잘림**: 현재 모델 입력 한도가 128 토큰인데 문서 평균이 97 토큰이고 3건(0.3%)이 잘린다.
  리뷰가 길어지면 비율이 오르고, 하필 뒷부분에 결론("재구매 의사 있어요")이 오는 경우가 많다.
- **모델 교체 검토**: 현재 `paraphrase-multilingual-MiniLM-L12-v2`는 대칭적 유사도용이다.
  이 프로젝트는 짧은 질의로 긴 리뷰를 찾는 비대칭 검색이라 `intfloat/multilingual-e5-small`
  (512 토큰, 384차원, 검색용 학습) 쪽이 구조적으로 맞다. 단 `query:` / `passage:` 접두어 규약 필요.
  → 질의를 바꿔가며 테스트해본 뒤 판단하기로 함. 지금은 보류.
- **저장 형식**: 벡터를 JSON 문자열로 저장 중이라 8.3MB. float32 BLOB이면 1.5MB.
  지금 규모에선 체감 없으나 데이터가 늘면 먼저 손볼 곳.
- **명소 추천 데이터** 미착수 (GOAL 필요데이터 항목).

---

## 2026-08-17
## 작업일지
> 색인과 검색을 파일로 분리하고, 낡은 색인을 감지하는 안전망을 넣었다.
> 코드 상세는 `src/src.md` 참고.

### 1. embed.py → build_index.py + search.py 분리

한 파일이 색인과 검색을 모두 하고 있어서, 검색 결과만 확인하려 해도 1439건을 다시
인코딩하는 16초를 치러야 했다. 역할로 나눴다.

- `build_index.py` — 색인 생성 전용 (`fetch_rows` / `build_doc` / `save_vectors`)
- `search.py` — 검색 전용 (`VectorStore` / `build_where` / `fmt_purchase_id`)
- `query.py` — 대화형 CLI. 입력·출력·로깅만 담당하고 검색은 `search.py`에 위임

이름을 `embed.py`로 두지 않은 이유는, 분리 후에는 **`search.py`도 임베딩을 하기 때문**이다
(질의 문장 인코딩). "embed"가 더 이상 이 파일을 구별해주지 못한다. 이 파일을 구별하는 것은
결과를 DB에 영속화한다는 점이고, `load_db.py`와 동사+목적어 형태로 짝도 맞는다.

`load_db.py`와 합치는 안도 검토했으나 택하지 않았다. `load_db.py`는 표준 라이브러리만
쓰는데(import 0.005초), 합치면 데이터 적재만 하려 해도 torch가 필요해진다
(`sentence_transformers` import만 6.5초). 대신 `.vscode/tasks.json`에 순서를 묶어뒀다.

### 2. VectorStore — 벡터를 한 번만 읽는다

기존 `search()`는 질의마다 `review_vectors` 전체를 읽어 JSON을 다시 파싱했다.
1439건 × 384차원이면 질의 한 번에 10MB가 넘는 파싱이고, 실측 0.157초였다.
시작 시 한 번만 메모리에 올리고 이후에는 `WHERE`로 걸러진 `purchase_id`만 받아 쓰도록 바꿨다.

```
VectorStore 생성  6.3초 (1회)  /  질의 1회  0.01~0.04초
```

### 3. check_freshness — 낡은 색인 감지

`load_db.py`를 다시 돌리고 `build_index.py`를 잊으면 `review_vectors`만 옛 데이터를
가리킨 채 남는다. 조인은 `purchase_id`로 조용히 성립하므로 **에러 없이 엉뚱한 리뷰가
검색된다.** 실제로 겪기 쉬운 사고인데 감지 수단이 없었다.

`embedding_meta`에 `source` 지문(`건수:ID합:리뷰길이합`)을 추가하고, `VectorStore` 생성 시
모델명과 지문을 현재 DB와 비교해 경고한다. 검색을 막지는 않는다 — 색인이 조금 낡아도
확인용으로는 쓸 만하고, 중단시키면 데이터를 손보는 중에 아무것도 못 하게 된다.

색인 대상 조건은 `config.py`의 `INDEX_FILTER`로 옮겼다. 색인과 검색이 같은 기준을 봐야
비교가 성립하는데, 두 곳에 적어두면 어긋난다.

### 4. 측정값 갱신

데이터가 1035건 → **1439건**으로 늘어 문서 수치가 어긋나 있었다. 토큰 길이도 다시 쟀다.

| 항목 | 2026-08-12 기록 | 현재 |
| --- | --- | --- |
| 색인 대상 | 1035건 | 1439건 |
| 128토큰 초과 (잘림) | 3건 (0.3%) | **11건 (0.8%)** |
| 토큰 중앙값 | 97 | 99 |

위 "남은 과제"의 토큰 잘림 항목이 예상대로 악화되고 있다. 메타데이터 접두부가 중앙값
56토큰으로 예산의 절반 가까이를 쓰고, 리뷰 본문이 맨 뒤라 잘리는 쪽은 본문이다.

### 5. 더미데이터 불일치 재확인 및 수정

2026-08-12에 적어둔 두 가지를 실제 데이터로 다시 확인했다.

**건식/습식 모순 → 0건.** 그 사이 데이터가 갱신되면서 해소됐다. `건식사료` 29건 전부
`target_food_form='건식'`, `습식사료` 20건 전부 `습식`이다.

**체급 불일치 → 30건 수정.** 문장 단위로 전수 조사하니 자기지칭 템플릿 2종이 잘못 쓰이고 있었다.

| 문장 | 정상 | 모순 |
| --- | --- | --- |
| `소형견용 작은 사이즈로 찾다가 발견했어요.` | 소형 16 | 중형 18, 대형 6 |
| `대형견이라 그런지 사료값이 만만치 않아서...` | 대형 41 | 소형 3, 중형 3 |

행의 실제 `size_category`에 맞는 문구로 바꿨다(중형 → `중형견용 사이즈로...`, 대형 →
`대형견용 큰 사이즈로...`, 사료값 문장은 소형·중형에서 체급 언급을 제거).

`크기가 적당해서 소형견도 먹기 편해요` 류 26건은 **손대지 않았다.** 대형견 주인이 상품을
일반적으로 평한 문장이지 자기 개가 소형견이라는 뜻이 아니다. 실제 리뷰에도 흔한 표현이다.

CSV를 통째로 다시 쓰면 인용 방식이 달라져 diff가 전체로 번지므로, 해당 줄 안에서 문장만
치환했다. BOM·CRLF·따옴표 개수(114)가 그대로 보존되고 30행만 바뀐 것을 확인했다.

### 6. check_data.py — 정합성 검사 단계 신설

§5에서 체급 문장을 고칠 때마다 매번 손으로 SQL을 두드리고 있었다. 검사 수단이 코드로
남아있지 않으니 다음 사람이(또는 다음 주의 내가) 같은 조사를 처음부터 다시 하게 된다.
`load_db.py`와 `build_index.py` 사이에 넣는 검사 단계로 정식화했다.

`sentence_transformers`를 import 하지 않아 torch 없이 돈다(`load_db.py`와 같은 이유).
11개 검사를 `ERROR`/`WARN` 2단계로 나누고, `ERROR`가 있으면 exit 1 이라 태스크 체인에서
자동으로 멈춘다. 전부 `ERROR`로 두면 데이터를 손보는 중에 아무것도 못 하게 되므로,
색인을 막아야 하는 것만 `ERROR`다 — `check_freshness()`와 같은 태도다.

**그리고 돌려보니 §5에서 고친 것보다 깊은 층위의 문제가 나왔다. ERROR 9건 / WARN 4건.**

가장 심각한 것은 **`pet_purchases`와 `pet_profiles`가 서로 다른 데이터**라는 점이다.
견종 어휘가 한쪽에만 8종/2종 있고(`코카스파니얼`↔`코커스패니얼`, `푸들`↔`토이푸들` 포함),
같은 `pet_id`인데 `breed` 1383건 / `weight_kg` 1422건 / `allergy` 885건이 어긋난다.
`pet_id` 조인은 성립하므로 **에러 없이 엉뚱한 프로필의 리뷰가 근거로 나간다.**
§3의 `check_freshness()`가 색인과 데이터 사이에서 잡는 것과 같은 종류의 조용한 실패가,
테이블 사이에서 일어나고 있었다.

원인은 좁혀진다. 목적·형태 별점 신호는 살아 있다(매칭 4.26 vs 비매칭 3.69). 이 수치는
`pet_profiles`를 조인해 잰 것이므로 **`rating`은 프로필을 제대로 보고 생성됐다**는 뜻이다.
비정규화 컬럼을 채우는 패스만 프로필을 참조하지 않고 독립적으로 값을 뽑은 것으로 보인다.

나머지 두 가지:

- **`size_category` 45건이 체중·견종과 모순.** 체중으로 유도한 체급과 견종으로 유도한 체급이
  서로 어긋나는 행은 **0건**이다. 즉 틀린 것은 `size_category` 컬럼 하나뿐이고,
  `weight_kg`에서 유도하면 해결된다. (39kg짜리 "소형견 셰퍼드"가 그대로 임베딩되고 있었다.)
- **알레르기 값 205/288건이 어떤 성분명과도 매칭될 수 없다.** `pet_purchases`는
  `닭고기 알레르기`라는 문구, `pet_products.ingredients`는 `닭고기`라는 성분명이라
  표기 체계가 다르다. 그 결과 알레르기 충돌이 22건뿐이고, `DATAINFO.md` §4.1이 명시한
  신호(충돌 시 평균 1.82)가 측정되지 않는다 — 실측 3.77로 기준선 3.87과 차이가 없다.
  **별점을 근거로 삼는 추천 로직이 지금은 근거를 잃은 상태다.**

상세 내역과 재생성 담당자용 수정 명세는 **`docu/DATAISSUE.md`** 에 따로 정리했다.

한편 §5에서 고친 체급 자기지칭 문장은 **0건으로 유지되고 있다.** 참조 무결성, 나이대↔나이,
상품 분류↔급여 형태도 통과했다.

---

## 2026-08-26
## 작업일지
> 색인 단위를 리뷰에서 조각으로 옮겼다. `review_vectors`를 없애고
> `chunks` + `chunk_vectors`로 전환한 뒤, 검색기를 그 구조에 맞게 다시 설계했다.

### 1. build_index.py — 지휘만 남기고 비웠다 (133줄 → 52줄)

`build_doc`/`fetch_rows`는 `prepare.py`에, `save_vectors`는 `prep/storage.py`에 이미
옮겨져 있어 중복이었다. `main()` 하나만 남겨 `prepare.py`와 대칭 구조로 만들었다.

```
prepare.py     : pet_purchases 읽기 → build_doc → split_reviews → save_chunks
build_index.py : load_chunks       →            → embed_texts   → save_vectors
```

삭제하지 않고 남긴 이유는 `save_vectors(con, chunks, vectors, dim, source)`의 인자를
완성해 넘길 자리가 필요해서다. `source` 지문 계산은 부르는 쪽 몫이다.

### 2. storage.load_chunks() 신설

`chunks`를 읽는 코드가 저장소 어디에도 없었다. `chunks` 스키마를 아는 SQL을
CREATE/INSERT와 한 파일에 모으려고 `storage.py`에 뒀다. 읽은 순서를 그대로 넘겨야
한다 — `save_vectors`가 조각과 벡터를 자리로 zip 하므로 재정렬하면 어긋난다.

### 3. embedding.py — 두 겹으로 깨져 있었다

`get_model()`이 `if _model is None:` 안에서 지역변수에 대입하고 `return _model`(항상
None)이었다. 그걸 고쳐도 `HuggingFaceEmbeddings`엔 `.encode()`가 없어 `embed_texts()`가
`AttributeError`로 죽는다. `SentenceTransformer`로 되돌렸다 — 시그니처가 원래 그쪽용이고,
numpy를 돌려줘 `.shape[1]`/`.tolist()`가 그대로 되며, 래퍼는 `encode_kwargs`를 생성
시점에 고정해서 질의 1건마다 진행 바를 끌 수 없다.

### 4. VectorStore 재설계

| 문제 | 처리 |
|---|---|
| `FROM review_vectors` | `chunk_vectors JOIN chunks` (본문은 `chunks.body`) |
| `row_of = {pid: i}` | `rows_of = defaultdict(list)` |
| `search()`의 벡터 테이블 조인 | 제거. 조인하면 리뷰 1건이 조각 수만큼 중복된다 |
| `argsort[:top_k]` | `purchase_id`별 최고점으로 접은 뒤 자른다 |

`row_of`를 그대로 뒀다면 리뷰당 마지막 조각만 남아 **4,172개 중 2,733개(65%)가 조용히
사라졌을 것이다** (리뷰 1,439건 중 1,359건이 조각 2개 이상).

집계는 평균이 아니라 최댓값이다. 조각들이 `CHUNK_OVERLAP`만큼 겹쳐 있어 평균은 신호를
희석시키고, 찾는 것은 "이 리뷰의 어느 한 대목이 질문과 맞는다"이기 때문이다.

### 5. review_vectors 제거 · tasks.json 수리

코드 참조 0건을 확인하고 테이블 DROP + VACUUM (`48.1MB → 36.0MB`). `db.py`/`eval.py`
주석도 갱신했다.

`tasks.json`은 문구가 아니라 실행이 깨져 있었다. `args`가 `src/build_index.py`인데 파일은
`pipeline/`으로 옮겨졌고, 파일 경로로 실행하면 `app.core` import가 깨진다. `-m` 모듈
실행으로 바꾸고 빠져 있던 `prepare`를 넣어 3단계로 만들었다.

### 측정

```
리뷰 1,439건 → 조각 4,172개 (토큰 평균 36.5 / 중앙값 33 / 최대 77)
chunk_vectors 4,172행 384차원, chunks와 1:1 (고아 0 / 누락 0), L2 노름 1.0
VectorStore 기동 경고 0건
```

---

### 남은 과제 (누적)

- **`"passage:"` 단독 조각이 1,359개(전체의 32.6%)다.** (2026-08-26 확인) 문서가 `passage:\n`
  으로 시작하는데 분할기 구분자에 `"\n"`이 있어 첫 줄바꿈에서 잘린다. 정작 내용이 든 조각
  2,813개에는 접두어가 없다. 아래 `passage:` 접두어 항목과 같은 뿌리다.
- **프로필 정보가 랭킹에 거의 기여하지 않는다.** (2026-08-26 확인) 질의 300건 기준 상위 10위
  조각의 96.6%가 `chunk_index=2`(품종·체급·상품명이 떨어져 나간 리뷰 꼬리)였다. `build_doc()`이
  앞에 붙인 맥락은 `chunk_index=1`에 갇혀 거의 안 뽑힌다. `CHUNK_SIZE=75`가 문서 길이에 비해 작다.
- **중복 제거는 현재 데이터에서 거의 발동하지 않는다.** 질의 300건 × top_k=10에서 4건(1.3%)뿐.
  위 두 항목이 고쳐지면 실제로 일하게 될 코드라 남겨뒀다.
- `check_freshness()`가 조각 재생성을 못 잡는다. 지문은 `pet_purchases`만 보므로 `CHUNK_SIZE`만
  바꿔 `prepare`를 다시 돌려도 경고가 없다. SQLite는 FK 검사가 기본 꺼짐이라 `DROP`도 안 막는다.
- `eval.py:42`가 `VectorStore.search(con, model, …)`로 인스턴스 없이 부른다 (이전부터 깨져 있음).
- `retrieve.py`가 `embedding.get_model()`을 안 쓰고 `SentenceTransformer`를 직접 만든다.
  모델을 바꿀 때 고칠 자리가 둘이다.

- **데이터 재생성이 선행 과제가 됐다.** `docu/DATAISSUE.md` §1~§3을 고쳐
  `check_data.py`가 `ERROR 0건`을 낼 때까지. 이게 정리되기 전에는 모델 A/B 비교를 해도
  적중률 차이가 모델 차이인지 데이터 노이즈인지 분리되지 않는다.
- **더미데이터 생성 스크립트가 저장소에 없다.** 이번엔 `data/*.csv`를 직접 고쳤으므로,
  데이터를 다시 생성하면 같은 문제가 재발한다. 체급 자기지칭 문장은 행의 `size_category`에
  맞춰 뽑도록 생성 쪽을 고쳐야 근본 해결이다.
- 위 2026-08-12 항목 대부분 유효. 특히 **토큰 잘림**과 **모델 교체**는 같이 풀린다
  (`multilingual-e5-small`은 512토큰).
- `is_holdout`이 현재 전량 0이라 holdout 설계가 미확정 상태다. 평가 방식이 정해져야
  `INDEX_FILTER`의 `is_holdout = 0` 조건이 실제로 의미를 갖는다.
- `check_freshness()`의 지문은 길이가 같은 오타 수정 같은 변경을 놓친다. 값싼 안전망이지
  검증이 아니다. 엄밀함이 필요해지면 리뷰 본문 해시로 바꿔야 한다.
- **`passage:` 접두어가 절반만 적용돼 있다.** `build_doc()`은 문서 앞에 `passage:`를 붙이는데
  (커밋 `306471d`), 현재 모델은 e5 계열이 아니고 `VectorStore.search()`의 질의 인코딩에는
  `query:` 접두어가 없다. 이 규약은 **쌍으로** 붙여야 의미가 있다. e5로 교체하면 규약이
  완성되고, 교체하지 않으면 접두어를 빼야 한다. 어느 쪽이든 재색인이 필요하므로
  "일단 보류"가 공짜가 아니다 — 모델 교체 판단과 같이 결정해야 한다.

## 2026-08-29
## 작업일지
> `eval.py`를 고쳐 recall@3을 처음으로 실측했다. 12.7% → 14.3% → 19.7% 세 단계로 올렸고,
> 각 단계에서 원인을 홀드아웃 케이스를 직접 까서 확인했다.

### 1. 검색 필터 버그 2건 — `retrieve.py`

`FILTERS["animal_category"]`가 리뷰어 반려동물이 아니라 **상품이 지원하는 축종**을 보고
있어서, 개 프로필로 검색해도 고양이 리뷰가 섞여 나왔다. `FILTERS["allergy"]`는 반대로
**상품의 원료 알레르겐**이 아니라 리뷰어 반려동물의 알레르기 등록 여부를 보고 있었다 —
소고기 알레르기라고 입력해도 상품에 소고기가 들었는지는 전혀 안 걸렀다. 둘 다 조인 대상을
바꿔 고쳤다(축종은 `pet.animal_category_id`, 알레르기는
`product_ingredient` → `ingredient_allergen` 경로).

### 2. eval.py 복구 — 2026-08-26에 남긴 과제 그대로였다

`VectorStore.search(con, model, …)`를 인스턴스 없이 부르는 죽은 코드였다(위 남은 과제
항목). `pipeline/vector_db.py`의 `search()`/`connect()`로 갈아탔다. 같이 깨져 있던 것:

- `load_holdout()`이 `purchase`에 없는 컬럼(`size_category`, `allergy`, `review`)을 그대로
  셀렉트하고 있었다 — `review`는 `review` 테이블 조인, `size_category`는 `CASE`로 파생.
- `evaluate()` 시그니처에 안 쓰는 `model` 인자가 남아 있었다.
- `__main__`이 `sqlite3.connect()`로 직접 열어 `sqlite_vec` 확장이 로드 안 된 커넥션을
  썼다 — `vec_distance_cosine` 함수를 못 찾고 죽었다. `vector_db.connect()`로 교체.

첫 실측: **recall@3 8/63 (12.7%)**.

### 3. `build_review_doc` 보일러플레이트 제거 — 12.7% → 14.3%

홀드아웃 미스 케이스를 직접 까보니(top-50 랭킹 전체를 찍어봄) 관련 없는 상품들 점수가
0.868~0.874 안에 뭉쳐 있었다 — 품종도 축종도 다른데 코사인 유사도가 거의 안 갈렸다.
원인은 `build_review_doc()`이 `size_category`/`breed`/`allergy`를 문장에 넣고 있었던 것.
이 값들은 이미 `retrieve.py`의 `FILTERS`가 SQL `WHERE`로 걸러주므로, 임베딩 문장에
또 넣으면 모든 문서가 거의 같은 템플릿이 되어 실제 구별 신호(상품명·리뷰 본문)를
희석시킨다. 세 필드를 빼고 카테고리/상품명/급여목적/제형/리뷰만 남겼다.

### 4. `gen_seed.py`에 원료 슬롯 추가 — 14.3% → 19.7%

더 깊은 원인: 리뷰 더미데이터 자체가 상품을 구별 못 하게 생성되고 있었다.
`review_body()`가 쓰는 재료(`PURPOSE_REASON`/`CATEGORY_REASON`/`TASTE`/`FORM_NOTE`/
`SIZE_NOTE`/`AGE_NOTE`)가 전부 "카테고리 단위" 슬롯이라, 같은 카테고리·같은 급여목적인
상품끼리는 리뷰 본문이 통계적으로 구별되지 않았다. `product.description`엔 이미 시리즈별
원료 배합이 구체적으로 있는데(`그레인프리랩 사료 02호` = "닭가슴살·연어·백미",
`04호` = "계육분·양고기·연어") `review_body()`가 이걸 전혀 안 썼다. `product_ingredient`를
`gen_purchases()`까지 배관해서 원료 언급 슬롯을 50% 확률로 추가했다.

### 측정

```
recall@3 :  8/63 (12.7%)  최초 실측 (eval.py 복구 직후)
recall@3 :  9/63 (14.3%)  보일러플레이트 제거
recall@3 : 13/66 (19.7%)  원료 슬롯 추가 (데이터 재생성으로 홀드아웃 표본 수 변동)
```

미스 63~66건을 4갈래로 나눠 추적했다(홀드아웃 리뷰 → `search()` top-50 전체에서 정답
상품 순위 확인):

| 갈래 | 뜻 |
|---|---|
| 필터가 정답상품 자체를 거름 | 프로필 필터 조건과 정답이 애초에 안 맞음 |
| top50에도 안 잡힘 | 정답 상품 색인 리뷰가 있어도 랭킹 밖 — 21/66, 아직 안 풀림 |
| top3 밖(랭킹은 있음) | 랭킹엔 있으나 3위 안에 못 듦 |
| top3 적중 | recall 카운트되는 것 |

### 남은 과제

- **"top50에도 안 잡힘" 21/66(32%)이 원료 슬롯으로도 안 줄었다.** 슬롯이 50% 확률이라
  안 붙은 리뷰가 여전히 애매한 것으로 보임 — 미스 케이스 중 원료 슬롯 있는/없는 비율을
  세보면 바로 검증됨. 다음 세션 시작점.
- `pipeline/chunk.py`의 size CASE(5단계: 초소형~초대형)와 `retrieve.py`의
  `FILTERS["size_category"]`(3단계: 소형/중형/대형만)가 안 맞는다. 급하지 않아 미룸.
- `gen_seed.py:325`(첫 품종만 보고 체구를 정함, 나머지 품종 무시)도 미룸 — 데이터
  재생성 비용 vs 효과가 아직 안 재짐.
- `app/main.py`가 여전히 옛 `VectorStore`(JSON)를 참조한다. `chunk_vectors`가 BLOB로
  바뀐 뒤로 죽어 있는 코드지만 `recommend.py`가 비어 있어 아직 안 터짐 — `vector_db.py`로
  갈아타야 함(`con.clost()` 오타도 같이).

## 2026-08-31
## 작업일지
> "top50에도 안 잡힘" 21/66을 이어서 팠다. `eval.py` 자체의 필터 누락을 먼저 잡고
> (recall@3 18.2% → 21.2%), 원료 슬롯 가설을 기각한 뒤, 미스 케이스를 직접 까서
> 두 갈래(데이터 오염 13.3% / 진짜 랭킹-변별력 문제 86.7%)로 쪼갰다.

### 1. `eval.py` 자체가 `animal_category` 필터를 빼고 측정하고 있었다

`load_holdout()`이 `animal_category`를 셀렉트하지 않아서, `evaluate()`/`diagnose_top50_miss()`가
`app/query.py`가 실제 사용자에게 주는 필터(종/체급/알레르기 3종) 중 종 필터 없이 측정하고
있었다 — 측정 대상과 실제 서비스 조건이 어긋나 있었다. `load_holdout()`에 `animal_category`
서브쿼리를 추가하고 `evaluate()`/`diagnose_top50_miss()`의 `build_where()` 호출에 반영.

recall@3 : 12/66 (18.2%) → 14/66 (21.2%)

### 2. 원료 슬롯 가설(2026-08-29 남은 과제) 기각

"top50 미스가 원료 슬롯 없는 리뷰에 쏠려 있다"를 `diagnose_top50_miss()`로 직접 세봄:
top50 미스 45.5% vs 적중 54.5% — 표본 크기(각 33건) 대비 표준오차(~8.7pp) 안이라 상관관계
없음. 이 가설은 폐기.

### 3. `inspect_misses()`로 미스 케이스 직접 열람 → 두 갈래로 분리

미스 5건을 정답/실제 top-3/점수와 함께 찍어보니 `product_id=183`(와일드포 사료 09호)이
두 번(purchase 1478, 1510) 등장. 1478은 구매자 반려동물의 등록 알레르기(참치)가 정답
상품에 실제로 들어있어 `FILTERS["allergy"]`(`retrieve.py:26-33`)가 정답 자체를 걸러낸
경우였다. `gen_seed.py:592`, `:652`는 구매 상품을 고를 때 `animal_category`만 보고
`pet_allergies`는 아예 안 본다 — 알레르기는 `review_body()` 후기 문장 생성에만 쓰인다.
그래서 "이 아이가 알레르기 있는 원료가 든 상품을 산" 모순된 구매가 만들어질 수 있다.

`is_allergy_contaminated()`/`count_allergy_contamination()`으로 전체 top50 미스 30건 중
몇 건이 이 패턴인지 세봄: **4/30 (13.3%)**. 나머지 26/30(86.7%)은 이 패턴이 아니다 —
1462, 1479는 top50 안에는 있는데(11위, 7위) 순위가 밀렸고, 무관한 1~3위 점수가 여전히
0.86~0.91 사이에 뭉쳐 있다(2026-08-29 §3에서 이미 지적된 것과 같은 현상, 그때 고친 건
프로필 필드 제거였지 이 압축 자체는 안 풀렸다).

### 원인 — `build_review_doc()`에 상품을 구별할 신호가 부족하다

`chunking.py:60-65`가 만드는 문서에 `product_name`은 들어가지만 **원료(ingredient) 목록은
안 들어간다.** 질의(`query:` 접두어, 사용자 후기/입력)에도 상품명이 없으니, 코사인 유사도는
사실상 "질의 문장이 문서의 후기 부분과 얼마나 비슷하냐"로 좁혀진다. 그런데 `gen_seed.py`의
`review_body()`가 만드는 후기는 상품별이 아니라 슬롯(구매 이유/식감/크기 등) 조합으로
찍혀나오는 템플릿이라, 같은 슬롯을 쓴 서로 다른 상품끼리 문서가 후기 본문 기준으로는
거의 같아진다 — 상품명 토큰 몇 개로는 이걸 못 이긴다.

### 4. `build_review_doc()`에 원료 목록 추가 → 재측정

`pipeline/chunk.py`의 `fetch_rows()`에 `product_ingredient`/`ingredient` LEFT JOIN을 추가해
`GROUP_CONCAT(DISTINCT ing.name_ko) AS ingredients`로 가져오고, `chunking.py`의
`build_review_doc()`이 `주원료: {ingredients}`를 문서에 넣도록 고침 (`size_category`/`breed`/`allergy`는
여전히 안 넣음 — FILTERS가 이미 SQL WHERE로 걸러줘서 넣으면 보일러플레이트만 늘어남).
재청킹(`chunk.py`) + 재임베딩(`embed.py`) 후 `eval.py`로 재측정:

```
recall@3 : 14/66 (21.2%) -> 16/66 (24.2%)
top50 미스 30건 -> 27건 (알레르기 오염 4건은 그대로 — 필터가 정답을 거른 거라 원료 신호로 못 고침)
```

미스 사례 중 반복 관찰되는 두 건의 순위가 눈에 띄게 올라감: purchase 1462(펫키친 트릿 01호)
11위 → 4위, purchase 1479(헬시포 간식 02호) 7위 → 5위. 방향은 진단대로 맞지만 top-3 밖이라
recall@3엔 안 잡힘. purchase 1478/1505는 여전히 top50 밖 — 1478은 §3에서 확인한 알레르기
오염 케이스라 원료 신호로 못 고치는 게 정상.

+3pp는 표본 66건의 표준오차(~5pp) 안이라 확신할 수치는 아니지만, 반복 케이스의 순위가 같은
방향으로 개선된 게 노이즈만은 아니라는 정황 근거. 합성 리뷰가 템플릿 슬롯 기반이라(gen_seed.py)
천장 자체가 낮고, 여기서 더 파는 것(임베딩 모델 교체, 리뷰 생성 로직 재작성 등)은 이 프로젝트
비용 대비 안 맞다고 판단 — **이 라인의 개선 작업은 여기서 정리.**

### 측정

```
recall@3 : 12/66 (18.2%)  eval.py의 animal_category 필터 누락 발견 시점
recall@3 : 14/66 (21.2%)  animal_category 필터 추가
top50 미스 30건 중 원료 슬롯 있음 비율 43.3% / 적중 36건 중 55.6%  (가설 기각, 노이즈 수준)
top50 미스 30건 중 알레르기 오염(정답이 필터에 걸림) 4건 (13.3%)
recall@3 : 14/66 (21.2%) -> 16/66 (24.2%)  build_review_doc()에 원료 목록 추가
top50 미스 30건 -> 27건 (알레르기 오염 4건 그대로 — 필터 문제라 원료 신호로 안 풀림)
```

### 남은 과제

- `eval.py`의 `is_allergy_contaminated()`/`count_allergy_contamination()`은 역할상
  recall 측정이 아니라 데이터 정합성 검사다 — `pipeline/check_data.py`로 옮기는 게
  아키텍처상 맞다. 급하지 않아 미룸.
- `has_ingredient_slot()`/`diagnose_top50_miss()`(2026-08-29에 추가, 위 §2에서 가설 기각)는
  `eval.py`에서 삭제함.


## 2026-09-01

### 리뷰 마스킹: 재현율이 아니라 오탐을 기준으로 규칙을 정했다

당근마켓류 글에 섞여 오는 연락처·주소·이름을 가리는 `app/domain/masking.py`. 규칙을 조일수록
우회는 더 잡히지만 평범한 후기가 먼저 지워진다. 어느 쪽을 택할지가 이 모듈의 유일한 설계 결정이고,
**새는 쪽을 택했다.** 사람이 손으로 다 거르지 못해서 자동 필터를 두는 거지 완벽하려고 두는 게 아니다.

감으로 정하면 틀린다는 걸 실측으로 확인했다. 이름 정규식에 `라고`("박승호라고 합니다")를 넣었더니
후기 2000건 중 **106건의 "-더라고요"** 를 통째로 먹었다. 규칙 하나의 대가는 코퍼스에 돌려보기
전에는 안 보인다. 그래서 `tests/domain_and_repo/masking.py` 끝에 `data/seed/review.csv` 전체를
돌려 **오탐 0건**을 확인하는 상한선을 박았다. 규칙을 조일 때마다 여기가 먼저 터지게 해뒀다.

같은 기준으로 걷어낸 것과 남긴 것:

- 걷어냄 — 시도 한 단어만으로 주소 판정(`부산광역시`). `부산 맛집처럼` 같은 말을 먹는다.
  행정구역이 두 단계 이상 이어질 때만 주소로 본다.
- 걷어냄 — `\W*` 를 구분자로 쓰던 것. 문장부호까지 먹어서 `오! 카레맛` 이 `오카`(오픈카톡)가 됐다.
  우회에 실제로 쓰는 기호만 화이트리스트로 받는다.
- 남김 — `사장|대표` 처럼 후기 코퍼스에 0건인 규칙. 한 번 지웠다가 되돌렸다. 판단 기준은
  "군더더기냐"가 아니라 **"정상 텍스트를 먹느냐"** 다. 안 먹으면 지울 이유가 없다.

### 마크를 종류별로 나눴다

전부 `[연락처]` 로 치환하던 것을 `(정규식, 대체어)` 쌍으로 바꿨다(`_RULES`). 무엇을 가렸는지가
글에 남아야 읽는 사람이 문맥을 잃지 않는다 — `[전화번호]`/`[이메일]`/`[연락처]`/`[아이디]`/
`[주소]`/`[이름]`. 마크가 줄줄이 붙으면 종류가 달라도 `[연락처]` 하나로 줄인다.

이름과 주소는 호출자가 목록을 넘겨야만 가려졌다(`names=`, `build_address_pattern(cities)`).
리뷰에 누가 나올지 미리 알 수 없으니 실패하는 설계다. 이름은 호칭·자기소개·조사가 붙은 자리로,
주소는 17개 시도를 상수로 박아 목록 없이 잡게 바꿨다. `build_address_pattern()` 은 삭제.
`names` 는 DB로 이미 아는 글쓴이·판매자 이름을 더 지우는 선택 인자로만 남겼다.

### 측정

```
후기 2000건 오탐 106건 -> 0건   (NAME 에서 '라고' 제거)
'라고' 브랜치가 먹던 것: '처음엔 먹다가 금방 남기더라고요' -> '... 금방 [이름]라고요'
지역번호 추가 후에도 오탐 0건  (02/031~064/070/080/0505 국번을 목록으로 박음.
                            \d{2,3} 으로 열면 '2026.08.13', '3000원에 1200g' 이 걸린다)
```

### 남은 구멍 (알고 두는 것)

`(031) 111-1111` 괄호 지역번호, `테헤란로 163` 도로명 단독, `오ㆍ픈` 화이트리스트 밖 기호,
성씨 없는 이름·외국 이름, 호칭도 조사도 안 붙은 맨 이름. 막으려면 구분자에 문장부호나 괄호를
넣어야 하는데 그 순간 `오! 카레맛` 이 돌아온다. 재현율이 정말 필요해지면 정규식이 아니라 NER 로 간다.

## 2026-09-01
## 작업일지
> 모델 비교 작업
> 임베딩 모델을 바꿀지 정하려다, 비교할 자(ruler)가 없다는 걸 먼저 발견했다. 낡은 색인과
> 쓰인 적 없는 홀드아웃 로직을 잡아 평가 신뢰구간을 21.2%p → 8.7%p 로 좁힌 뒤, 로컬 후보
> 3종을 같은 조건에서 재서 **통계적 동률**로 판정했다. e5-small 유지. 그 동률 자체가
> "모델은 병목이 아니다"라는 진단이라, 천장이 어디에 박혀 있는지 문장 단위로 세어 확인했다.

### 1. 모델을 갈아끼울 수 없는 구조였다 — 프로파일 도입

`query: `/`passage: ` 는 e5 계열 전용 포맷인데 코드 4곳(`chunking.py`, `embedding_text.py`,
`vector_db.py`, `query.py`/`searching.py`)에 리터럴로 박혀 있었다. bge 계열은 이 접두사를
붙이면 오히려 성능이 떨어지므로, 이 상태로 모델만 바꿔 재면 "bge 에 e5 접두사를 억지로
먹인 점수"가 나온다 — 비교 자체가 성립하지 않는다.

같은 문자열을 여러 곳에 적어서 이미 어긋나 있었다: `chunking.py` 는 `"passage: "`(콜론+공백),
`embedding_text.py` 는 `"passage:\n"`(콜론+줄바꿈). `query.py` 의 `removeprefix('passage: ')`
가 상품 문장에서는 접두사를 못 벗기고 있었다.

`config.py` 에 `EMBED_PROFILES` 표를 두고 차원/최대토큰/배치/접두사를 모델별로 모았다.
`EMBED_MODEL` 은 `env()` 로 읽어 셸에서 바꿀 수 있게 했고, `EMBED_TOKENIZER`/`EMBED_DIM`/
`EMBED_MAX_TOKENS`/`EMBED_BATCH_SIZE`/`QUERY_PREFIX`/`PASSAGE_PREFIX` 를 그 표에서 파생시켰다.
표에 없는 모델은 `SystemExit` 으로 즉시 막는다.

곁가지로 발견: **`load_env()` 가 정의만 되어 있고 호출되는 곳이 없었다.** `.env` 전체가
조용히 무시되고 있었다(`OPENAI_API_KEY`, `GOOGLE_CLIENT_ID`, `JWT_SECRET` 포함). 값이 안
읽혀도 에러 없이 기본값으로 굴러가서 알아채기 어려운 종류다. `env()` 정의 직후에 호출 추가.
`embed.py:47` 도 `EMBED_BATCH_SIZE`/`EMBED_NORMALIZE` 를 import 해놓고 리터럴 `32`/`True` 를
쓰고 있어 같이 고쳤다.

### 2. DB의 색인이 코드보다 낡아 있었다

재측정하니 `recall@3 : 13/66 (19.7%)`. 8/31 에 기록한 `16/66 (24.2%)` 보다 낮다.

원인: `chunks` 에 `주원료:` 를 포함한 행이 **0건**이었다. 그런데 `chunk.py:44,57-58` 에는
`product_ingredient`/`ingredient` 조인이 있고 `chunking.py:61` 에는 원료 슬롯이 있으며
`product_ingredient` 는 909행이 들어 있다. 즉 **코드에는 있고 DB에는 없다** — 8/31 의
원료 슬롯 수정 이후 `chunk.py` 가 다시 돌지 않았다. `inspect_misses()` 출력의
purchase 1462 순위가 8/31 기록의 "11위 → 4위" 중 **11위** 쪽과 정확히 일치해 확정.

재색인 후 `17/66 (25.8%)` 로 복구(기록된 16/66 과 1건 차이는 노이즈 범위).

`check_freshness()` 가 이걸 못 잡은 이유는 모델 이름만 대조하기 때문이다. `embed.py:50` 이
조각 지문(`source`)을 `embedding_meta` 에 남기는데 아무도 읽지 않았다. `dim` 과 `source`
대조를 추가했다(`chunk_fingerprint()`). 다만 이번처럼 **코드만 바뀌고 `chunk.py` 를 안 돌린**
경우는 여전히 못 잡는다 — 코드 지문까지 뜨는 건 과하다고 판단, "모델 실험할 땐 무조건
`chunk.py` 부터"를 습관으로 막기로 했다.

### 3. eval.py 를 비교 가능한 하네스로 개조

`evaluate()` 가 k 마다 결과를 다시 훑고 `print` 만 하고 버렸다. 표본별 **정답 순위 정수 하나**
(`rank_of_answer()`)만 구해두면 recall@k 도 MRR 도 전부 거기서 파생된다. `score_runs()` →
`summarize()` 로 나누고, `save_run()` 이 모델명으로 `data/eval/<model>.json` 에 남기게 했다.
모델을 바꾸면 `chunk_vectors` 가 DROP 되므로 이전 모델 결과는 DB 에 안 남는다 — 비교하려면
DB 밖에 남기는 수밖에 없다.

`noise_band()`(부트스트랩 2000회)로 **자의 정밀도를 먼저 쟀다**. 66건 기준
`recall@3 95% 구간 15.2% ~ 36.4%` — 폭 21.2%p, 건수로 14건. 이 상태로는 어떤 두 모델도
구별할 수 없다는 뜻이라, 표본을 먼저 손봐야 했다.

`measure_query_latency()` 도 추가. 색인은 배포 때 한 번이지만 질의 인코딩은 요청마다
일어나므로, 품질이 뭉칠 때 결정을 가르는 축이 된다.

### 4. 홀드아웃이 잘못 잡혀 있었다 — 66건 → 275건

`prep_rec.py` 의 `mark_holdout()`("고객별 최근 구매 1건")이 **이 DB 에 실행된 적이 없었다.**
리뷰 있는 유저가 275명이므로 그게 돌았다면 275건이어야 하는데 DB 에는 66건.

`purchase_id` 구간별 홀드아웃 비율로 출처를 특정:

```
   0 ~  999 : 0.0%   ← 원본 CSV 이식분 (gen_seed.py:614, src 값 그대로 = 전부 0)
1000 ~ 1499 : 1.2%   ← 경계
1500 ~ 1999 : 11.4%  ← 합성 보충분 (gen_seed.py:668, rng < 0.10)
2000 ~      : 7.5%
```

66건이 **전부 합성 구간에서만** 나왔다. 문제 셋:
- **편향** — 앞의 약 1450건(원본 이식분)은 평가에 한 번도 안 쓰였다.
- **독립성 위반** — 66건이 펫 58마리에 걸쳐 있고 8마리는 2건 이상. 부트스트랩은 독립을
  가정하므로 실제 노이즈는 측정치보다 넓다.
- **누수** — 홀드아웃이 유저별 최근순 rn=1~15 로 흩어져 있어, rn=5 짜리는 그 뒤에 쓴 리뷰
  4건이 색인에 있는 상태로 평가된다. 미래를 보고 과거를 맞히는 셈.

`mark_holdout()` 실행으로 셋 다 해소(전 구간 / 유저당 1건 / 마지막 구매). `prep_rec.py` 의
`main()` 은 `mark_holdout` 과 벡터 빌드를 한 번에 돌리는데, 그 사이에 `chunk.py`→`embed.py`
가 끼어야 하므로(`build_customer_vectors` 가 `chunk_vectors` 를 읽는다) `holdout`/`vectors`
인자로 쪼갰다.

**`rn <= 3`(796건)으로 더 늘리지 않은 이유**: `INDEX_FILTER` 가 `is_holdout=0` 만 색인하므로
평가셋을 늘리면 색인이 얇아진다. `rn<=3` 이면 색인 1764→1243, 상품 4개가 색인 리뷰 0건이
되고 **홀드아웃 20건은 정답이 검색 결과에 존재조차 하지 않아 영구 오답**이 된다. 자를
정밀하게 만들려다 재는 대상을 부수는 셈. 표본 수 상한은 "원리적으로 못 맞히는 표본이
생기기 직전"까지다.

### 5. 로컬 모델 3종 비교 → 통계적 동률, e5-small 유지

같은 조건(홀드아웃 275건 / 색인 1764조각)에서 모델마다 `chunk.py`→`embed.py`→`eval.py`.
토크나이저와 접두사가 모델에 종속이므로 **반드시 `chunk.py` 부터** 다시 돈다.

같은 275개 질의를 셋이 풀었으므로 표본별로 짝지어 MRR 차이를 부트스트랩(4000회)했더니
**세 쌍 모두 95% 구간이 0을 포함**했다. @3 뒤집힘도 반반이다. 지표마다 이기는 모델이
다른 것(r@1 은 base, r@10 은 m3, MRR 은 small)도 실재하는 차이가 아니라 노이즈의 서명이다.

판정 규칙은 측정 전에 정해뒀다: **MRR 주지표, 노이즈 겹치면 동률, 동률이면 차원 낮고 빠른 쪽.**
→ `intfloat/multilingual-e5-small` 유지. bge-m3 대비 질의 인코딩 9.5배 빠르고 벡터 용량 1/2.6.
`vector_db.py:100` 이 인덱스 없는 전수 스캔이라 차원이 낮은 게 스캔 비용에도 그대로 이득이다.

결론이 "안 바꾼다"인 게 실패는 아니다. 재보고 남긴 기본값과 안 재보고 남긴 기본값은 다르다.

`compare.py`(신규)의 판정 로직에 결함이 있어 고쳤다 — 24:24 를 "A 우세 0건"으로 찍었다.
한쪽 우세가 `√(뒤집힘)` 보다 작으면 동률로 판정하게 수정.

### 6. 천장이 어디에 박혀 있는지 — 모델이 아니라 데이터다

세 모델 동률은 "뽑을 신호를 이미 다 뽑았다"는 뜻이라, 리뷰 2039건을 문장 단위로 쪼개 확인:

```
전체 문장 10,432개 -> 서로 다른 문장 1,603개  (한 문장이 평균 6.5번 재사용)
한 문장이 걸친 상품 수: 중앙값 1 / 상위10% 5 / 최대 182
리뷰 한 건이 담은 '그 상품에서만 나오는 문장' 개수 -> 0개 1045건 / 1개 921건 / 2개 73건
```

**리뷰의 51.3%(1045건)는 그 상품을 특정하는 문장이 하나도 없다.** `"그릇을 비우는 걸 보니
마음이 놓여요"` 는 182개 상품에 걸쳐 나온다. 텍스트에 없는 정보를 복원하는 임베딩 모델은
없으므로, 이 천장은 모델 교체로 안 올라간다. 8/31 의 "합성 리뷰가 템플릿이라 천장이 낮다"는
판단이 수치로 확인됐다.

다만 **더 큰 문제는 평가 과제가 서비스와 다르다는 것**이다. `searching.py:20` 의 실제 질의는
사용자가 타이핑한 요구인데 `eval.py:113` 은 리뷰 본문을 넣는다. 정답도 `product_id` 정확
1개라, `펫키친 트릿 01호` 산 사람에게 `스노우독 트릿 01호`(같은 카테고리·급여목적)를 준
것을 0점 처리한다. 서비스에서는 그게 정상 동작이다. 즉 18.9% 는 시스템 성능이 아니라
**지표의 엄격함**일 가능성이 크다. 고칠 것은 모델이 아니라 대용품(proxy) 쪽이다.

`small vs m3` 가 48건이나 뒤집혔는데 24:24 인 것은 두 모델이 서로 다른 24건씩을 찾는다는
뜻이라 보통은 앙상블이 유리하다. 인코딩 비용 2배(145ms) 대비 얻을 게 적고 데이터 천장이
낮아 **안 하기로 함** — 몰라서 안 한 게 아니라 재보고 안 한 것으로 기록.

### 7. 태스크화

`.vscode/tasks.json` 에 「📊 모델 비교 (조각 -> 색인 -> 평가)」 추가. `inputs.pickString` 으로
모델을 고르고 `options.env` 로 그 태스크 프로세스에만 `EMBED_MODEL` 을 주입한다 — 셸 환경을
오염시키지 않고 `.env` 의 `setdefault` 도 이긴다. Windows PowerShell 5.1 에는 `&&` 가 없어
`$LASTEXITCODE` 로 앞 단계 성공을 확인한다(`;` 로만 이으면 `chunk.py` 가 실패해도 `embed.py`
가 낡은 조각을 임베딩해 조용히 오염된 결과가 남는다).

`prep_rec.py holdout` 은 **일부러 태스크에 넣지 않았다.** 평가셋 자체를 바꾸므로 비교 도중
실수로 눌리면 A/B 가 서로 다른 문제를 푼 게 된다. 원클릭으로 만들면 안 되는 작업이 있다.

### 측정

```
[낡은 색인 발견 ~ 복구]
recall@3 : 13/66 (19.7%)  낡은 색인(원료 슬롯 없음) 상태로 측정
recall@3 : 17/66 (25.8%)  chunk.py + embed.py 재실행 후 복구
recall@3 95% 구간 15.2% ~ 36.4%  (폭 21.2%p) — 66건 표본으로는 모델 구별 불가

[홀드아웃 66 -> 275 (mark_holdout), 색인 1973 -> 1764]
recall@1   24/275 =  8.7%   95% 구간  5.8% ~ 12.4%  (폭  6.5%p)
recall@3   52/275 = 18.9%   95% 구간 14.5% ~ 23.3%  (폭  8.7%p)   ← 21.2%p 에서 좁힘
recall@10  96/275 = 34.9%   95% 구간 29.5% ~ 40.4%  (폭 10.9%p)
top50 밖 108/275

[로컬 모델 3종 (홀드아웃 275건 / 색인 1764조각 고정)]
model      dim      r@1      r@3     r@10      mrr    query_ms   벡터용량
e5-small   384     8.7%    18.9%    34.9%   0.1745      13.8ms    2.6 MB
e5-base    768    10.2%    17.8%    30.5%   0.1690      41.3ms    5.2 MB
bge-m3    1024     6.9%    18.9%    36.4%   0.1643     131.6ms    6.9 MB

[짝지은 부트스트랩 4000회 — MRR 차이 95% 구간, 0 포함이면 동률]
small -> base   -0.0055  [-0.0299, +0.0187]  동률
small -> m3     -0.0101  [-0.0385, +0.0180]  동률
 base -> m3     -0.0047  [-0.0327, +0.0216]  동률

[@3 뒤집힘]
small vs base   17:14 (총 31)   small vs m3   24:24 (총 48)   base vs m3   15:18 (총 33)

[데이터 천장]
문장 10,432개 -> 서로 다른 문장 1,603개 (평균 6.5회 재사용, 최대 182개 상품에 걸침)
'그 상품에서만 나오는 문장'이 0개인 리뷰 1045/2039 (51.3%)
```

### 남은 과제

- **상용 API 비교**. `EMBED_PROFILES` 와 `compare.py` 가 있어 프로파일 한 줄로 붙는다.
  단 **Anthropic 은 임베딩 API 를 제공하지 않는다**(공식 문서가 Voyage AI 로 안내) —
  실제 비교 대상은 OpenAI `text-embedding-3-small/large` / Voyage / Cohere `embed-multilingual-v3`.
  Claude 는 이 프로젝트에서 `config.py` 의 LLM 자리(추천 문장 생성)이지 임베딩 자리가 아니다.
- **`.claude/skills/pet-reco/SKILL.md` 와 `docs/SKILL.md` 가 없는 파일을 가리킨다.**
  `load_db.py`/`check_data.py`/`prepare.py`/`build_index.py`/`pipeline/query.py` → 실제는
  `load_csv.py`/`chunk.py`/`embed.py`/`app/query.py`. `/pet-reco` 는 지금 전부 실패한다.
- `check_freshness()` 는 데이터 지문만 보므로 "코드만 바뀌고 `chunk.py` 를 안 돌린" 경우를
  못 잡는다. 코드 지문까지 뜨는 건 과하다고 판단해 습관으로 대체.