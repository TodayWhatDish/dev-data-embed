## 작업일지

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