# SCHEMA.md — 컬럼 레퍼런스

`src/create_schema/create_schema.py` 의 컬럼 단위 설명. DDL 을 읽기 쉽게 두려고 주석을 여기로 뺐다.

- **왜** 그렇게 설계했는지(테이블 단위 판단)는 `DESIGN.md` 를 본다. 이 문서는 **무엇이 있는지**만 다룬다.
- 이 문서와 `create_schema.py` 가 어긋나면 **코드가 맞다.** 스키마를 고치면 여기도 같이 고친다.

---

## users

서비스 가입자(보호자) 계정. 반려견·구매·리뷰의 최상위 소유자이며, 삭제 시 하위 데이터가 함께
정리된다(`ON DELETE CASCADE`).

상태 컬럼을 두지 않는다 — '휴면'은 `last_login_at` 에서 계산되는 파생값이라 컬럼으로 굳히면
휴면 기준 정책이 바뀔 때마다 전 행을 갱신해야 한다.

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `user_id` | INTEGER | PK | 대리키. rowid 별칭이라 조회/조인이 가장 빠르다 |
| `auth_provider` | TEXT | NOT NULL, DEFAULT `'local'`, CHECK | 신원을 확인해 준 주체. `google`/`firebase`/`kakao`/`apple`/`local` |
| `auth_uid` | TEXT | NOT NULL | 제공자가 준 불변 고유 ID. 로그인 시 계정 조회 키 |
| `email` | TEXT | NOT NULL, UNIQUE | 연락/표시용 이메일 |
| `name` | TEXT | NOT NULL | 보호자 이름(표시용) |
| `phone` | TEXT | | 연락처 |
| `region` | TEXT | | 활동 지역(시/도). 명소 추천(3단계)과 배송권역에 쓰인다 |
| `last_login_at` | TEXT | CHECK datetime | 마지막 로그인 시각. '휴면 계정'을 여기서 계산한다 |
| `withdrawn_at` | TEXT | CHECK datetime | 탈퇴 시각. NULL = 활성 |
| `created_at` | TEXT | NOT NULL, DEFAULT `datetime('now')` | 가입 시각 |
| `updated_at` | TEXT | NOT NULL, DEFAULT `datetime('now')` | 마지막 수정 시각 |

**인덱스**

| 이름 | 컬럼 | 목적 |
|---|---|---|
| `uq_users_auth` | UNIQUE (`auth_provider`, `auth_uid`) | 같은 외부 계정이 두 유저에 붙는 것을 DB 레벨에서 차단 |

### 설계 노트

**`user_id` 는 우리 서비스의 유저 식별자다.** 하위 테이블이 참조하는 소유자 키는 오직 이 값이다.

**`auth_uid` 는 로그인 순간에만 읽힌다.** 이메일이 아니라 이 값으로 계정을 찾는다 — 이메일은
사용자가 바꿀 수 있지만 이 값은 안 바뀐다. 로그인 이후 요청은 토큰에서 복원한 `user_id` 만 쓴다.
로그인 처리는 `uq_users_auth` 를 그대로 타는 조회 하나로 끝난다:

```sql
SELECT user_id FROM users WHERE auth_provider = ? AND auth_uid = ?
```

복합 UNIQUE 인 이유는 이 **쌍**이 유일해야 하기 때문이다 — 같은 uid 라도 제공자가 다르면 다른 계정이다.
두 컬럼 모두 등호 조건이라 컬럼 순서는 성능에 영향을 주지 않는다.

**`auth_provider` CHECK 에 미사용 값을 미리 넣어뒀다.** SQLite 는 CHECK 를 바꾸려면 테이블을
재생성해야 한다. 값을 넓게 잡아두는 건 공짜고, 안 쓰면 그만이다. Firebase Auth 를 경유하면
`'firebase'`(uid 는 Firebase UID), 구글 OAuth 를 직접 붙이면 `'google'`(uid 는 ID token 의 `sub`)이다.
기본값은 자체 계정(`'local'`).

**`email` 은 NOT NULL UNIQUE 다.** 자체 계정(`local`)에서는 로그인 ID 역할을 하고, 구글은 항상 검증된
이메일을 주므로 양쪽 다 성립한다. 이메일을 안 주거나 미검증으로 주는 제공자(카카오는 선택 동의)를
붙이는 날 이 제약은 완화해야 한다.

**`phone` 에 UNIQUE 를 걸지 않는다.** 가족 공유, 통신사 번호 재할당, 탈퇴 후 재가입 때문에 실제로
유일하지 않다. 로그인 수단도 아니다.

**`withdrawn_at` — 불리언 `is_del` 대신 시각을 저장한다.** 개인정보 보관기간 경과분 파기 배치가
'언제 탈퇴했는지'를 필요로 하기 때문이다.

**`created_at` 에 인덱스를 걸지 않는다.** 범위 조회 수요가 생긴 뒤에 추가한다.
