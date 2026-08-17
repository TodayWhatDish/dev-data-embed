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
- [ ] **원료 추가 시 백필한다.** 중간 카테고리를 넣을 때는 **위에서부터** 순서대로.

```sql
INSERT OR IGNORE INTO pet_allergies(pet_id, allergen_id)
SELECT pet_id, :new_id FROM pet_allergies WHERE allergen_id = :parent_id;
```

### 인증

- [ ] **`user_id` 는 검증된 토큰에서만 꺼낸다.** 요청 body·쿼리스트링으로 받지 않는다.
- [ ] **`local` 계정을 실제로 쓸 거면 두 가지를 먼저 정한다** — 비밀번호 해시를 둘 자리(`users` 에는 없다.
      `user_credentials` 분리 권장)와, 외부 제공자가 없을 때 `auth_uid` 를 무엇으로 채울지.

### 개인정보

- [ ] **탈퇴는 `withdrawn_at` 갱신이다. `DELETE` 가 아니다.**
- [ ] **보관기간 경과분 파기도 `DELETE` 가 아니라 익명화 `UPDATE` 로 한다.** `users` 행을 지우면
      `ON DELETE CASCADE` 로 `pets` 와 그 아이가 남긴 후기까지 사라진다. 후기는 이 저장소의 핵심 자산이다.

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

`src/create_schema/` 에 아직 없는 것들. (2026-08-17 기준 15 테이블 + 2 뷰)

- [x] `ingredients` — 원료 마스터. `allergen_id` 가 안전 판정의 연결 고리
- [x] `products` / `product_animal_categories` / `product_ingredients` / `product_nutrition`
- [x] `feeding_purposes` / `product_feeding_purposes` / `product_categories`
- [x] `v_product_safety` / `v_safe_products` — 알러지 3분법 판정
- [ ] **C블록** `purchases`
- [ ] **C블록** `reviews`
- [ ] **D블록** `review_embeddings`
- [ ] 남은 뷰 (`v_pet_context`, `v_review_docs`) — C블록 이후에나 만들 수 있다

C·D블록이 들어갈 자리는 `src/create_schema/` 에 모듈을 하나씩 더 만들고
`execute_schema.MODULES` 끝에 붙이면 된다 (예: `purchase_schema.py`).

## 4. 이관 마무리

- [ ] CSV 로더를 새 스키마(`user.db`)로 포팅
- [ ] 임베더를 새 스키마로 포팅 (벡터는 JSON 텍스트가 아니라 BLOB)
- [ ] `data/*.csv` 를 새 스키마 형태로 재생성 (현재는 옛 4테이블 기준)
- [ ] `src/make_db/` 제거
- [x] `README.md` / `CLAUDE.md` 경로 참조 정리 (2026-08-17)
- [ ] `DESIGN.md` 본문 갱신 — 경로뿐 아니라 내용이 코드와 어긋난다 (`WORK.md` 참조)
