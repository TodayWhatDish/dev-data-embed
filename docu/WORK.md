## 작업일지

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

`user.db` 재생성, `load_db.py` 재작성, 더미 CSV 재생성, `embed_reviews.py` 포팅.
상세는 `local/ToDo.md` §9.

## query.py

질문/체급/알레르기를 입력받아 프로필 조건으로 거른 벡터검색 결과를 보여주고 매 질문을 query_log.jsonl에 기록

## embed.py
config.py로 경로/모델명 분리, build_doc에 e5 전환 대비 "passage:\n" 접두어 추가(질의 쪽 "query:" 접두어는 아직 안 붙음, 모델도 아직 e5 아님).