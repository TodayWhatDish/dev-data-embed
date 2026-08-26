
## [패키지 설치]
>  python -m pip install langchain-text-splitters==1.1.2 transformers==5.14.1

>  python -m pip install langchain-huggingface==1.2.2


## [실행 순서]
0. Python : Select Interpriter 설정.
1. Task : Task Run에서 의존성 설치 (설정된 인터프리터에 설치됨.)
# TODO

스키마(`schema/`)에는 담기지 않지만 지켜야 하는 것들. **DB 가 강제하지 못하므로 앱·운영이 책임진다.**

---

## 1. 앱이 구현해야 하는 것

### 마스터 데이터 (`animal_categories` / `breeds` / `allergens`)

- [ ] **앱 기준 읽기 전용으로 다룬다.** 사용자 입력이 이 테이블들에 직접 INSERT 되는 경로를 만들지 않는다.
- [ ] **기동 시 통째로 읽어 메모리에 캐시한다.** 수백 행짜리 정적 데이터라 매 요청 조회할 이유가 없다.
- [ ] **관리자가 행을 추가하면 캐시를 비운다.** 트리 인식이 낡으면 알러지 팬아웃이 틀린 목록으로 들어간다.
- [ ] **품종은 드롭다운으로만 받는다.** 자유 입력을 허용하면 `'코커스패니얼'`/`'코카스파니엘'` 같은
      표기 흔들림이 다시 생긴다.
- [ ] **품종 드롭다운을 `animal_category_id` 로 필터해서 채운다.** 개인 `pet` 에 고양이 품종을 연결하는 것을
      DB 가 막지 않는다(`pet_breeds` 에 복합 FK 를 걸지 않기로 했다).

### 알러지

- [ ] **등록 시 하위를 전부 펼쳐 넣는다.** 앱이 캐시된 트리에서 하위 목록을 계산하고, **고른 카테고리 행도
      포함해서** 다중 INSERT 한다. 카테고리 행이 없으면 나중에 백필 대상을 찾을 수 없다.
- [ ] **순환 탐지 코드가 필요하다. INSERT·UPDATE 양쪽에서 호출한다.**

      DB 는 순환을 못 막는다. 두 가지 경로로 뚫린다.

      - `allergen_id` 를 명시한 INSERT 로 자기 자신을 부모로 지정할 수 있다 — `(5, 5)`. FK 는 통과시킨다.
      - `PRAGMA foreign_keys` 가 꺼진 상태(SQLite 기본값)로 적재하면 A→B→A 같은 긴 순환도 만들어진다.

      INSERT 냐 UPDATE 냐로 분기하지 말고 **"이 `(id, parent_id)` 관계를 반영하면 순환이 생기나"**
      를 판정하는 함수 하나를 두고 양쪽에서 호출한다. 분기가 없으면 빠뜨릴 곳도 없다.
      캐시된 트리에서 새 부모부터 위로 거슬러 올라가며 자기 자신을 만나는지만 보면 되므로
      깊이만큼(3~4회)만 돈다.

      ```python
      def creates_cycle(node_id, parent_id, parent_of):
          p = parent_id
          while p is not None:
              if p == node_id:      # 자기참조 (5,5) 도 첫 반복에서 걸린다
                  return True
              p = parent_of.get(p)
          return False
      ```

- [ ] **계층 재편(`parent_id` 이동)은 서비스 오픈 전에 끝낸다.** 계층을 바꾸면 이미 팬아웃된
      `pet_allergies` 행이 새 계층과 어긋난다. `단백질` 을 고른 사람은 그 시점 기준으로 펼쳐진 행을
      갖고 있어서, 나중에 `가금류` 가 중간에 생겨도 그 사람 행에는 없다.
- [ ] **원료를 등록할 때 알러지원 매핑을 같은 트랜잭션에서 넣는다.** `allergen_reviewed` 를 뺐으므로
      (2026-08-24) `ingredient_allergens` 0행은 곧 '알러지원 없음'으로 읽힌다. 매핑을 나중에
      넣기로 미루면 그 사이에 그 원료가 든 제품이 **`Safe` 로 통과한다** — 에러 없이 조용히.
      DB 가 못 막는 자리라 등록 UI/로더가 필수값으로 받아야 한다.
- [ ] **원료 추가 시 백필한다.** 중간 카테고리를 넣을 때는 **위에서부터** 순서대로.

```sql
INSERT OR IGNORE INTO pet_allergies(pet_id, allergen_id)
SELECT pet_id, :new_id FROM pet_allergies WHERE allergen_id = :parent_id;
```

### 나이

- [ ] **`purchases.age_month_at_purchase` 는 앱이 `petcalc.age_months()` 로 계산해 넣는다.**
      SQL 로 하면 `julianday` 차이를 30.44 로 나눠야 하는데 근사라 생일 근처에서 틀린다.
- [ ] **`pets.birth_date` 를 나중에 입력받으면 그 아이의 기존 구매를 백필한다.**
      안 하면 그 행들은 영영 NULL 이라 나이 기반 집계에서 빠진다.

### 체구

- [ ] **`pets.size` 를 고칠 때 그 이유를 구별해서 처리한다.** DB 는 못 구별한다.
      - **자랐다** (기본) → `pets.size` 만 UPDATE. 과거 `purchases.size_at_purchase` 는 그대로 둔다
      - **잘못 봤다가 정정** → 그 아이의 기존 `purchases.size_at_purchase` 도 같이 UPDATE
      구별이 필요하면 수정 UI 에 버튼이 두 개여야 한다. 하나뿐이면 '자랐다'로 처리한다 —
      모든 강아지가 자라고 오판은 일부다.

### 인증

- [ ] **`user_id` 는 검증된 토큰에서만 꺼낸다.** 요청 body·쿼리스트링으로 받지 않는다.
- [ ] **`local` 계정을 실제로 쓸 거면 두 가지를 먼저 정한다** — 비밀번호 해시를 둘 자리(`users` 에는 없다.
      `user_credentials` 분리 권장)와, 외부 제공자가 없을 때 `auth_uid` 를 무엇으로 채울지.

### 개인정보

- [ ] **탈퇴는 `withdrawn_at` 갱신이다. `DELETE` 가 아니다.**
- [ ] **보관기간 경과분 파기도 `DELETE` 가 아니라 익명화 `UPDATE` 로 한다.**
      2026-08-24 부터 `pets.user_id` 와 `purchases.pet_id` 가 **RESTRICT** 라 `users`/`pets` 행 삭제를
      DB 가 거부한다. 실수로 후기 전체를 날리는 경로가 막혔다.
- [ ] **익명화 대상은 사람으로 되돌아가는 값뿐이다.** `users.email`/`name`/`phone`/`auth_uid`/`region`,
      그리고 `pets.name`. 품종·체구·체중·알러지는 개인정보가 아니고 세그먼트 추천의 근거다 — 지우지 않는다.
- [ ] **`reviews.body` 를 따로 본다.** 자유 텍스트라 스키마가 통제하지 못한다.
      가족관계·지역·연락처가 본문에 그냥 들어온다. 파기 검토가 실제로 필요한 자리는 여기다.
- [ ] **삭제권(GDPR 17조) 행사는 별개 경로다.** RESTRICT 때문에 `reviews` → `purchases` → `pets` → `users`
      순서로 직접 지워야 한다. 여러 단계를 밟아야 하는 것이 안전장치다 — 한 줄로 되면 안 되는 작업이다.

---

## 2. 코드값 일관성

같은 뜻의 값이 테이블마다 다르게 매겨지면 **필터가 에러 없이 조용히 틀린다.**

- [ ] `products.target_size_min`/`max` 는 `pets.size` 와 같은 `1~5` 코드를 쓴다.
- [ ] `animal_category_id` 를 갖는 모든 테이블은 `animal_categories` 를 참조한다. 테이블마다 따로 매기지 않는다.

### 제품 분류 (2026-08-17 결정)

- [ ] **제품 하나에 분류 하나.** '사료 겸 간식'을 만들지 않는다 — 등록하는 사람이 간식이면 간식,
      사료면 사료로 무조건 하나를 고른다. 애매하면 "이것만 먹여도 되는가"로 가른다.
- [ ] **`product_categories` 는 2단계까지만 쓴다** (대분류 → 소분류). 소분류의 소분류를 만들지 않는다.
      DB 는 `parent_id` 로 3단계 이상을 막지 못하는데, 대분류 판정이
      `COALESCE(parent_id, product_category_id)` 한 칸 올라가기로 되어 있어
      3단계가 생기면 **손자가 자기 부모를 대분류로 보고**한다. 에러 없이 조용히 틀린다.

### 축종 (2026-08-17 결정)

- [ ] **개(1) / 고양이(2) 둘만 다룬다.** 앵무새·햄스터 등은 넣지 않는다.
- [ ] 축종을 늘리려면 `animal_categories` INSERT 만으로는 부족하다 — `breeds` 목록,
      `pets.size`/`body_type` 척도, 제품 급여 기준이 전부 그 축종용으로 딸려 와야 한다.
- [ ] **제품은 대상 축종을 반드시 등록한다.** `product_animal_categories` 에 행이 0개면
      그 제품은 아무 프로필에도 노출되지 않는다(의도된 fail-closed). 등록 UI 가 필수값으로 받아야 한다.

---

## 3. 스키마 남은 작업

**2026-08-26 기준 18 테이블 + 뷰 0개.** A·B·C블록 완료, D블록 미완.

- [x] A블록 — `users` / `pets` / `breeds` / `pet_breeds` / `pet_allergies` / 코드표
- [x] B블록 — `products` 외 8테이블, 알러지 판정
- [x] `safe_products.SAFE_PRODUCTS_SQL` — 알러지 3분법 판정 (2026-08-25 뷰에서 옮김)
- [x] C블록 — `purchases` / `reviews` (2026-08-25)
- [x] 구매 시점 스냅샷 — `age_month_at_purchase`(SQL 산술 회피), `size_at_purchase`(복원 불가)
      `weight_kg`(급여량은 현재 값), `neutered`(추천 입력이 아님)는 안 넣는다.
- [ ] **`idx_pets_segment`** — `pets(animal_category_id, size)`.
      세그먼트 조회("나랑 비슷한 애들이 뭘 샀나")의 선두 인덱스다. 실측(펫 10만 × 구매 200만):
      **97.76ms → 0.31ms.** `purchases` 가 없던 시절 미뤄뒀는데 이제 생겼다.
- [ ] **D블록** `review_embeddings` — `purchase_id` PK + 벡터 BLOB, `INSERT OR REPLACE`
- [ ] `v_pet_context` / `v_review_docs` — **뷰로 만들지 재검토.**
      판정 뷰를 뺀 이유(상관 서브쿼리, 로직 이원화)가 여기도 걸리는지 보고 정한다.

## 4. 이관 마무리

- [ ] CSV 로더를 새 스키마(`user.db`)로 포팅
- [ ] 임베더를 새 스키마로 포팅 (벡터는 JSON 텍스트가 아니라 BLOB)
- [ ] `data/*.csv` 를 새 스키마 형태로 재생성 (현재는 옛 4테이블 기준)
- [ ] `src/make_db/` 제거
- [x] `README.md` / `CLAUDE.md` 경로 참조 정리 (2026-08-17)
- [ ] `DESIGN.md` 본문 갱신 — 경로뿐 아니라 내용이 코드와 어긋난다 (`WORK.md` 참조)
- [ ] CSV 의 `age`(정수) → `birth_date` 역산 규칙 정하기.
      기준일을 오늘로 잡느냐 `updated_at` 으로 잡느냐에 따라 최대 1년 어긋나고,
      그렇게 만든 생일은 추정값인데 정확한 값과 구별되지 않는다.
- [ ] `docu/schema/*.md` 문단 구조 정리 — `purchase_schema.md` 는 컬럼별 `####` 로 나눴다(2026-08-26).
      나머지 넷은 굵은 문단이 평평하게 이어진다 (`product_schema.md` 47개, `pet_schema.md` 29개).
