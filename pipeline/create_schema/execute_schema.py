# Last Updated: 2026-08-17
"""
'오늘 뭐먹냥' user.db 스키마 — 실행 진입점.

DDL 은 도메인별 모듈에 있고, 이 파일은 그것을 **모아서 순서대로 실행**하기만 한다.
파일 구성은 docu/schema/ 문서 구성과 1:1 로 맞췄다.

    common_schema.py   animal_category, allergen          (공유 코드표)
    user_schema.py     user
    pet_schema.py      breed, pet, pet_breed, pet_allergy
    product_schema.py  제품 8테이블 + 뷰 2개
    purchase_schema.py purchase, review

모듈 계약 — 각 모듈은 아래 이름을 **있는 것만** 모듈 수준 리스트로 노출한다.
없으면 빈 리스트로 친다.

    TABLES         list[str]                      CREATE TABLE 문
    INDEXES        list[str]                      CREATE INDEX 문
    UNIQUE_INDEXES list[str]                      CREATE UNIQUE INDEX 문 ('자연키' 강제)
    VIEWS          list[str]                      CREATE VIEW 문
    SEEDS          list[(str, list[tuple])]       (INSERT 문, 파라미터 행들)

DROP 목록은 모듈이 갖지 않는다 — 이유는 drop_all() 주석 참고.

MODULES 의 순서가 곧 생성 순서다. 의존이 있는 쪽이 뒤에 온다:
    common (의존 없음) -> user (의존 없음) -> pet (common, user) -> product (common, pet)
    -> purchase (pet, product)
purchase 가 맨 뒤인 이유는 pet 와 product 를 둘 다 참조하기 때문이다.
테이블의 FK 는 참조 대상이 아직 없어도 CREATE 가 되지만, 뷰는 안 된다.
순서가 틀어지면 check_fk_targets() 가 잡는다.

---------------------------------------------------------------------------
설계 규칙 (전 모듈 공통)

  1) 모든 PK 는 INTEGER PRIMARY KEY (SQLite rowid 별칭).
     - 테이블 B-tree 가 정수로 직접 키잉되어 별도 인덱스가 생기지 않는다.
     - 조인이 문자열 비교가 아니라 64비트 정수 비교가 된다.
     - SQLite 에 unsigned 타입은 없다. uint32/uint64 는 STRICT 에서 에러이고,
       비STRICT 에서도 그냥 INTEGER 로 해석될 뿐 아무 제약이 없다.
       INTEGER 는 값 크기에 따라 1~8바이트로 가변 저장되므로 폭 지정도 무의미하다.

  2) 다대다 연결 테이블은 번호 컬럼을 따로 두지 않고, 두 FK 를 묶어서 PK 로 쓴다.

     "한 마리가 여러 품종을 갖고, 한 품종은 여러 마리가 갖는다"를 이렇게 표현한다.

         pet_breed
         ┌────────┬──────────┐
         │ pet_id │ breed_id │
         ├────────┼──────────┤
         │      3 │        1 │  초코 - 포메라니안  ┐ 초코는 믹스라 2행
         │      3 │        7 │  초코 - 치와와      ┘
         │      5 │        1 │  보리 - 포메라니안
         └────────┴──────────┘
          └──── 이 둘을 합쳐서 PRIMARY KEY ────┘

     pet_breed_id 같은 번호를 붙이지 않는 이유:
       - (pet_id, breed_id) 조합이 이미 행 하나를 정확히 가리킨다.
       - 그 번호를 FK 로 참조할 다른 테이블이 없다. 붙여도 아무도 안 쓴다.
       - PK 로 잡아두면 "초코에게 포메라니안을 두 번 등록"이 그냥 막힌다.
         번호를 PK 로 두면 이걸 막는 UNIQUE 인덱스를 따로 챙겨야 하고,
         빠뜨리면 중복이 조용히 들어간다.

     조회 방향에 따라 인덱스가 다르다. PK 는 앞 컬럼 기준으로만 정렬돼 있다.
       WHERE pet_id = 3    -> PK 의 앞 컬럼이라 그대로 탄다. 추가 인덱스 불필요.
       WHERE breed_id = 1  -> PK 를 못 탄다. 이 방향을 쓴다면 인덱스를 따로 만든다.

     끝에 WITHOUT ROWID 를 붙인다. 그러면 PK 가 곧 테이블의 저장 순서가 되어
     인덱스라는 별도 구조가 아예 생기지 않는다.

  3) 상태(status)를 저장하지 않고 사실(타임스탬프)만 저장해 파생시킨다.
     휴면 = last_login_at 에서 계산, 탈퇴 = withdrawn_at IS NOT NULL.

  4) 날짜/시각은 TEXT ISO-8601. SQLite 에 DATE 타입이 없으므로 CHECK 로 형식만 강제한다.
     ISO-8601 을 쓰는 이유는 표기 통일뿐 아니라 정렬 때문이다 —
     'YYYY-MM-DD' 는 사전순 == 시간순이라 문자열 비교만으로 범위 조회와 ORDER BY 가 성립한다.
     날짜 컬럼에 단독 인덱스는 걸지 않는다. 실제 조회가 "특정 반려견의 최근 구매"처럼
     항상 부모 ID 로 먼저 좁혀지므로, 필요해지면 (pet_id, purchased_at) 복합으로 만든다.
     purchased_at 단독 인덱스는 전체 기간 통계 같은 관리자 쿼리에나 쓰이는데,
     그건 빈도가 낮아 풀스캔으로 충분하다.

  5) 금액은 INTEGER(원 단위). REAL 은 반올림 오차가 생긴다.

  6) 불리언은 INTEGER + CHECK IN (0,1). SQLite 에 BOOL 이 없다.
     현재 대상: pet.neutered, product.ingredients_verified, product.is_active,
     review.is_holdout. review.allergy_reaction 은 NULL 을 더 허용한다(= 후기에 언급 없음).

  7) STRICT 테이블 — 손실 없이 변환되지 않는 값은 INSERT 가 거부된다. 끄지 않는다.
     "타입이 다르면 거부"가 아니다. INTEGER 컬럼 기준으로 실측하면:

         '30000'    -> 통과 (integer 30000 으로 저장)
         '30000.0'  -> 통과
         3.0        -> 통과
         '삼만원'    -> 거부: cannot store TEXT value in INTEGER column
         3.5        -> 거부: cannot store REAL value in INTEGER column

     그래서 CSV 로더가 문자열을 int()/float() 로 미리 캐스팅할 필요는 없다 —
     숫자로 읽히는 문자열은 그대로 넣어도 선언한 타입으로 들어간다.
     막아주는 것은 그대로다: STRICT 가 없으면 '삼만원' 이 INTEGER 컬럼에 TEXT 로
     조용히 앉아 있다가 나중에 비교·정렬에서 틀린 답을 낸다.
     끄는 스위치를 두지 않으므로 상수로 빼지 않고 DDL 에 그대로 적는다.

실행: py src/create_schema/execute_schema.py   (repo root 에서, SQLite 3.37+ 필요)
      PATH 의 python 이 3.9(SQLite 3.35)면 STRICT 를 파싱하지 못한다. py 로 실행할 것.
"""

import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common_schema
import user_schema
import pet_schema
import product_schema
import purchase_schema

DB_PATH = 'user.db'

# 순서가 곧 생성 순서다. 의존이 있는 쪽이 뒤.
MODULES = (common_schema, user_schema, pet_schema, product_schema, purchase_schema)

# 모듈에서 걷어오는 이름. 실행 순서이기도 하다 —
# 테이블이 다 생긴 뒤에 인덱스, 그 다음 뷰, 시드는 맨 마지막(FK 검증을 켜고 넣는다).
DDL_KINDS = ('TABLES', 'INDEXES', 'UNIQUE_INDEXES', 'VIEWS')


def collect(kind):
    """전 모듈에서 kind 리스트를 MODULES 순서대로 이어붙인다."""
    out = []
    for mod in MODULES:
        out.extend(getattr(mod, kind, ()))
    return out


def drop_all(con):
    """sqlite_master 에 있는 것을 전부 지운다.

    모듈마다 DROP 목록을 따로 두지 않는 이유: 목록과 실제 테이블이 어긋나면
    옛 테이블이 유령으로 남는다. 실제로 겪었다 — 옛 스크립트가 만든
    purchase/review/review_embeddings 가 DROP 목록에 없어서 계속 살아남아
    객체 수가 17개로 잡혔다. 여기서는 '무엇을 만들었는지'가 아니라
    '지금 무엇이 있는지'를 보고 지우므로 그 어긋남 자체가 생기지 않는다.

    이 스크립트의 계약은 '전체 재생성'이다(증분이 아니다). db_path 를
    다른 DB 로 돌리면 그 DB 도 비워진다.
    """
    views = [n for (n,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'view'")]
    tables = [n for (n,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    for name in views:
        con.execute(f'DROP VIEW IF EXISTS "{name}"')
    for name in tables:
        con.execute(f'DROP TABLE IF EXISTS "{name}"')
    return len(tables), len(views)


def check_fk_targets(con):
    """모든 FK 의 참조 대상 테이블이 실재하는지 확인한다.

    SQLite 는 없는 테이블을 가리키는 FK 로도 CREATE TABLE 을 통과시킨다.
    그래서 MODULES 순서가 틀어지거나 테이블명에 오타가 나도 생성은 성공하고,
    나중에 INSERT 할 때가 되어서야 터진다. 여기서 미리 잡는다.
    """
    tables = {n for (n,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
    broken = []
    for t in sorted(tables):
        for row in con.execute(f'PRAGMA foreign_key_list("{t}")'):
            target = row[2]
            if target not in tables:
                broken.append(f'{t} -> {target}')
    if broken:
        raise RuntimeError('없는 테이블을 가리키는 FK: ' + ', '.join(broken))


def owners():
    """객체명 -> 모듈명. 인벤토리를 모듈별로 묶어 보여주려고 DDL 에서 이름을 뽑는다."""
    pat = re.compile(r'CREATE\s+(?:UNIQUE\s+)?(TABLE|VIEW|INDEX)\s+([A-Za-z_][\w]*)', re.I)
    out = {}
    for mod in MODULES:
        for kind in DDL_KINDS:
            for ddl in getattr(mod, kind, ()):
                m = pat.search(ddl)
                if m:
                    out[m.group(2)] = mod.__name__
    return out


def report(con):
    """모듈별로 무엇이 생겼는지, 시드가 몇 행 들어갔는지 출력한다."""
    own = owners()
    rows = con.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()

    for mod in MODULES:
        mine = sorted(n for k, n in rows if own.get(n) == mod.__name__)
        print(f'\n[{mod.__name__}]')
        for name in mine:
            kind = next(k for k, n in rows if n == name)
            seeded = ''
            if kind == 'table':
                (cnt,) = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()
                if cnt:
                    seeded = f'  (시드 {cnt}행)'
            print(f'  {kind:5} {name}{seeded}')

    n_tab = sum(1 for k, _ in rows if k == 'table')
    n_view = sum(1 for k, _ in rows if k == 'view')
    (n_idx,) = con.execute(
        "SELECT count(*) FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
    ).fetchone()
    print(f'\n{n_tab} tables, {n_view} views, {n_idx} indexes')

    orphan = [n for _, n in rows if n not in own]
    if orphan:
        print(f'[경고] 어느 모듈에서 왔는지 알 수 없는 객체: {orphan}')


def create_schema(db_path=DB_PATH, verbose=True):
    con = sqlite3.connect(db_path)
    try:
        # DROP 중에는 FK 를 끈다. 부모를 먼저 지워도 걸리지 않게 하기 위해서다.
        con.execute('PRAGMA foreign_keys = OFF')
        dropped = drop_all(con)

        for kind in DDL_KINDS:
            for ddl in collect(kind):
                con.execute(ddl)
        con.commit()

        # PRAGMA foreign_keys 는 트랜잭션 안에서 무시되므로 commit 뒤에 켠다.
        # 시드를 FK 검증이 켜진 상태로 넣어야 product_category 의 parent_id 같은
        # 자기참조가 실제로 검사된다.
        con.execute('PRAGMA foreign_keys = ON')
        for sql, rows in collect('SEEDS'):
            con.executemany(sql, rows)
        con.commit()

        check_fk_targets(con)
        if verbose:
            if any(dropped):
                print(f'기존 객체 삭제: 테이블 {dropped[0]}개, 뷰 {dropped[1]}개')
            report(con)
    finally:
        con.close()


if __name__ == '__main__':
    create_schema()
