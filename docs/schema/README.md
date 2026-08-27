# schema/ — 컬럼 레퍼런스

`src/create_schema/` 의 컬럼 단위 설명. DDL 을 읽기 쉽게 두려고 주석을 여기로 뺐다.

- **왜** 그렇게 설계했는지(테이블 단위 판단)는 각 테이블의 **설계 노트** 절에 있다.
  `../DESIGN.md` 는 2026-08-13 기준이라 B블록(제품) 이후가 반영돼 있지 않다 —
  다대다 규칙·테이블 수·뷰 목록·알러지 3분법이 지금과 다르니 그대로 믿지 않는다.
- 이 문서와 `src/create_schema/` 가 어긋나면 **코드가 맞다.** 스키마를 고치면 여기도 같이 고친다.
- 설계 규칙(정수 PK / STRICT / ISO-8601 / 복합 PK + `WITHOUT ROWID` 등)은 `execute_schema.py` 의
  docstring 에 있다. 여기서 되풀이하지 않는다.

**코드 파일이 이 문서 구성과 1:1 로 대응한다.** 스키마를 고칠 때 짝이 되는 파일을 같이 고치면 된다.

| 문서 | 코드 |
|---|---|
| `README.md` | `src/create_schema/execute_schema.py` (진입점 + 설계 규칙) |
| `common_schema.md` | `src/create_schema/common_schema.py` |
| `user_schema.md` | `src/create_schema/user_schema.py` |
| `pet_schema.md` | `src/create_schema/pet_schema.py` |
| `product_schema.md` | `src/create_schema/product_schema.py` |

실행: `py src/create_schema/execute_schema.py` (repo root 에서)

**현재 16 테이블 + 2 뷰.** C블록(구매/후기)과 D블록(임베딩)은 아직 새 스키마로 포팅되지 않았다.

---

## 파일 지도

| 파일 | 담는 것 | 테이블 |
|---|---|---|
| [common_schema.md](common_schema.md) | **두 도메인이 공유하는 코드표** | `animal_category`, `allergen` |
| [user_schema.md](user_schema.md) | 계정 | `user` |
| [pet_schema.md](pet_schema.md) | 반려동물 | `breed`, `pet`, `pet_breed`, `pet_allergy` |
| [product_schema.md](product_schema.md) | 제품 | `product_category`, `feeding_purpose`, `product`, `product_animal_category`, `product_nutrition`, `product_feeding_purpose`, `ingredient`, `ingredient_allergen`, `product_ingredient` + 뷰 2개 |

**`common_schema.md` 가 따로 있는 이유** — 이 두 코드표는 반려동물 쪽과 제품 쪽이 **같은 ID 를
참조해야만** 성립한다. 한쪽 도메인 파일에 넣으면 다른 쪽에서 읽을 때 "왜 저기 있지"가 된다.

| 코드표 | 반려동물 쪽 | 제품 쪽 | 같은 ID 를 써야 하는 이유 |
|---|---|---|---|
| `animal_category` | `breed`, `pet` | `product_animal_category` | 고양이 제품이 개 후보에 섞이면 안 된다 |
| `allergen` | `pet_allergy` | `ingredient_allergen` | 알러지 배제가 문자열이 아니라 **조인**이 되려면 |

---

## 관계도

```
                    animal_category ─────┐
                     │            │        │
                     │            │        │
        ┌────────────┘            │        └──────────┐
        │                         │                   │
     breed                     pet              product_animal_category
        │                     │  │  │                       │
        └── pet_breed ───────┘  │  └── pet_allergy       │
                                 │              │           │
                              user ────────────┼───────────┼──────┐
                                                │           │      │
                                          allergen         │   product
                                                │           │    │ │ │ │
                                     ingredient_allergen ──┘    │ │ │ └─ product_category
                                                │                │ │ │
                                          ingredient            │ │ └─ product_nutrition
                                                │                │ │
                                       product_ingredient ──────┘ │
                                                                   │
                                       product_feeding_purpose ───┘
                                                │
                                        feeding_purpose
```

**뷰 없음 (2026-08-25).** 알러지 판정 뷰 2개를 빼고 `src/safe_products.py` 로 옮겼다 —
뷰의 `EXISTS` 가 상관 서브쿼리라 후보 제품마다 알러지 조인을 다시 돌았다(5.62ms → 2.20ms).

---

## 이 스키마가 반드시 지키는 것

문서를 흩어놓아도 이 세 가지는 파일을 가로질러 성립해야 한다.

**① 알러지 배제는 SQL 이 한다. LLM 이 아니다.**
LLM 은 확률적으로 실패하지만 `NOT EXISTS` 는 반드시 배제한다.
판정 로직이 있는 곳은 `src/safe_products.py` 의 `SAFE_PRODUCTS_SQL` **한 군데**다.

**② 모르는 것을 안전으로 처리하지 않는다.**
데이터가 부실할수록 더 안전해 보이는 실패를 막기 위해, 판정은 `WARN`/`None`/`Safe` 3분법이다.
판정 로직은 뷰가 아니라 `src/safe_products.py` 에 있다 (2026-08-25).
같은 원칙이 `product_animal_category` 의 0행(= 아무에게도 안 뜸)에도 적용된다.

**③ 사실을 저장하고 상태는 파생시킨다.**
나이는 `birth_date` 에서, 휴면은 `last_login_at` 에서, 재구매는 구매 행에서 계산한다.
100g당 가격은 `price_krw` / `weight_g` 에서 나온다.

---

## 스키마에 담기지 않는 규칙

DB 가 강제하지 못해 앱·운영이 책임지는 것들은 [`../docu.md`](../docu.md) 에 있다
(알러지 트리 순환 참조 방지, 축종 정합성, 마스터 캐시 무효화 등).
