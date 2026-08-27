# Last Updated: 2026-08-25
"""
data/master + data/seed 의 CSV 를 user.db(16테이블 스키마)로 적재한다.

    data/master/*.csv ┐
                      ├─> load_csv.py ─> user.db
    data/seed/*.csv   ┘

옛 src/load_db.py 를 대체한다. 그쪽은 4테이블 비정규화 스키마 전용이고,
DDL 까지 스스로 만들었다. 여기서는 DDL 을 만들지 않는다 — 스키마의 단일 원천은
src/create_schema/ 이고, 이 파일은 그것이 만든 테이블에 값을 넣기만 한다.

**적재 순서를 손으로 적지 않는다.** 부모가 아직 없는 테이블에 INSERT 하면 FK 검증에 걸려
멈추므로 순서가 중요한데, 그 정답은 이미 DDL 안에 있다 — `PRAGMA foreign_key_list` 가
"이 테이블이 무엇을 참조하는가"를 알려준다. 그래프를 위상 정렬하면 순서가 나온다.
사람이 옮겨 적으면 스키마와 어긋날 수 있고, 어긋난 채로도 운 좋게 돌다가
테이블이 하나 늘어난 날 터진다.

순서는 두 층이다. 같은 topo_sort() 를 양쪽에 쓴다.

    테이블 사이 : users 가 pets 보다 먼저      -> resolve_order()
    한 테이블 안 : allergens 의 부모 행이 먼저  -> order_rows_parents_first()

두 번째가 따로 필요한 이유는 자기참조(allergens.parent_id -> allergens) 때문이다.
테이블 레벨에서는 자기 자신을 기다리게 되므로 그래프에서 빼고, 행 레벨에서 푼다.

CSV 규약은 src/make_data/gen_seed.py 의 docstring 에 있다. 여기서 되풀이하지 않는다.
값 캐스팅은 하지 않는다 — STRICT 테이블이 '30000' 을 INTEGER 30000 으로 받아주고
'삼만원' 은 거부하므로, 파이썬에서 미리 int() 를 부르면 같은 검사를 두 번 하는 셈이다
(근거는 execute_schema.py 설계규칙 7번). 빈 칸 -> NULL 변환만 한다.

실행: py src/load_csv.py            (스키마를 새로 만들고 적재. 기존 user.db 는 비워진다)
      py src/load_csv.py --keep     (스키마를 그대로 두고 적재만)
"""

import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'create_schema'))

from execute_schema import create_schema  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'user.db'
MASTER_DIR = ROOT / 'data' / 'master'
SEED_DIR = ROOT / 'data' / 'seed'

# 테이블 -> CSV 경로. **순서를 적지 않는다.**
# 적재 순서는 resolve_order() 가 FK 관계에서 계산한다. 손으로 적으면 스키마와 어긋날 수 있고,
# 어긋난 채로도 '운 좋게' 돌다가 테이블이 하나 늘어난 날 터진다.
SOURCES = {
    # --- 마스터: 사람이 채운다. 재생성하지 않는다 ---
    'allergens': MASTER_DIR / 'allergens.csv',
    'breeds': MASTER_DIR / 'breeds.csv',
    'ingredients': MASTER_DIR / 'ingredients.csv',
    'ingredient_allergens': MASTER_DIR / 'ingredient_allergens.csv',
    # --- 합성: gen_seed.py 가 시드 고정으로 뽑는다 ---
    'users': SEED_DIR / 'users.csv',
    'pets': SEED_DIR / 'pets.csv',
    'pet_breeds': SEED_DIR / 'pet_breeds.csv',
    'pet_allergies': SEED_DIR / 'pet_allergies.csv',
    'products': SEED_DIR / 'products.csv',
    'product_animal_categories': SEED_DIR / 'product_animal_categories.csv',
    'product_nutrition': SEED_DIR / 'product_nutrition.csv',
    'product_feeding_purposes': SEED_DIR / 'product_feeding_purposes.csv',
    'product_ingredients': SEED_DIR / 'product_ingredients.csv',
}

# animal_categories / product_categories / feeding_purposes 는 여기에 없다.
# 코드(*_schema.py 의 SEEDS)가 넣는다. CSV 로 또 빼면 같은 값이 두 군데에 앉는다.
# 이 테이블들을 참조하는 FK 는 이미 채워져 있으므로 순서 계산에서 자동으로 빠진다.


# ---------------------------------------------------------------------------
# 순서 계산 — 무엇을 먼저 INSERT 해야 하는가

def topo_sort(items, key_of, deps_of, what):
    """의존 대상이 먼저 오도록 정렬한다(위상 정렬).

    "지금 넣을 수 있는 것"(= 의존 대상이 전부 처리된 것)만 골라 넣기를 반복한다.
    아무것도 못 고르는 순간이 오면 **순환**이거나 없는 대상을 가리키는 것이라 세운다.
    조용히 넘어가면 나중에 IntegrityError 로 터지고, 그때는 원인이 안 보인다.

        items    : 정렬할 것들
        key_of(x): x 의 식별자
        deps_of(x): x 보다 먼저 있어야 하는 식별자들 (set)

    테이블 순서와 행 순서 양쪽에 쓴다. 같은 문제라서 코드를 두 벌 두지 않는다.
    """
    pending = list(range(len(items)))    # 인덱스로 다룬다 — dict 행끼리 == 비교를 피한다
    done, out = set(), []
    while pending:
        ready = [i for i in pending if deps_of(items[i]) <= done]
        if not ready:
            stuck = ', '.join(str(key_of(items[i])) for i in pending[:5])
            raise RuntimeError(
                f'{what}: 순환하거나 없는 대상을 가리킨다 -> {stuck}'
                + (' ...' if len(pending) > 5 else ''))
        done |= {key_of(items[i]) for i in ready}
        out.extend(items[i] for i in ready)
        ready_set = set(ready)
        pending = [i for i in pending if i not in ready_set]
    return out


def parent_tables(con, table):
    """이 테이블의 FK 가 가리키는 **다른** 테이블들.

    자기참조(allergens.parent_id -> allergens)는 뺀다. 테이블 레벨에 두면 자기 자신을
    기다리느라 위상 정렬이 멈춘다. 자기참조는 행 레벨(order_rows_parents_first)이 맡는다.
    """
    return {row[2] for row in con.execute(f'PRAGMA foreign_key_list("{table}")')
            if row[2] != table}


def resolve_order(con, sources):
    """적재 순서를 DB 에게 물어서 계산한다.

    DDL 에 이미 정답이 들어 있다 — PRAGMA foreign_key_list 가 "이 테이블이 무엇을
    참조하는가"를 알려주므로, 그 그래프를 위상 정렬하면 순서가 나온다.

    적재 대상이 아닌 부모(코드 SEEDS 로 이미 채워진 animal_categories 등)는 조건에서 뺀다.
    이미 있는 것을 기다릴 이유가 없다.
    """
    names = set(sources)
    tables = sorted(names)               # 정렬해 두면 순서 계산이 결정적이다
    return topo_sort(tables, lambda t: t,
                     lambda t: parent_tables(con, t) & names,
                     '테이블 적재 순서')


def print_order(con, order):
    """계산된 순서와 그 근거(무엇을 기다리는가)를 보여준다."""
    print('\n[적재 순서] FK 관계에서 계산 — 손으로 적은 목록이 아니다')
    names = set(order)
    for i, t in enumerate(order, 1):
        deps = sorted(parent_tables(con, t) & names)
        outside = sorted(parent_tables(con, t) - names)
        why = f'  <- {", ".join(deps)}' if deps else ''
        seeded = f'   (시드 참조: {", ".join(outside)})' if outside else ''
        self_ref = '  [자기참조]' if self_fk_column(con, t) else ''
        print(f'  {i:>2}. {t:28}{why}{self_ref}{seeded}')


# ---------------------------------------------------------------------------

def columns_of(con, table):
    """{컬럼명: (notnull, 기본값있음)}. 헤더 검증에 쓴다."""
    return {row[1]: (bool(row[3]), row[4] is not None or bool(row[5]))
            for row in con.execute(f'PRAGMA table_info("{table}")')}


def self_fk_column(con, table):
    """자기 자신을 참조하는 FK 컬럼명. 없으면 None."""
    for row in con.execute(f'PRAGMA foreign_key_list("{table}")'):
        if row[2] == table:
            return row[3]
    return None


def order_rows_parents_first(rows, pk, fk):
    """자기참조 테이블의 **행**을 부모부터 나오도록 정렬한다.

    allergens 는 parent_id 로 자기를 가리키고 FK 검증이 켜져 있으므로, 자식이 먼저
    INSERT 되면 그 자리에서 터진다. CSV 를 손으로 편집하다가 행 순서가 바뀌는 것은
    흔한 일이라 파일 순서에 의존하지 않는다.

    테이블 순서와 같은 문제이므로 같은 topo_sort() 를 쓴다.
    """
    return topo_sort(rows, lambda r: r[pk],
                     lambda r: {r[fk]} if r[fk] else set(),
                     f'{fk} 행 순서')


def load_table(con, table, path):
    if not path.exists():
        raise FileNotFoundError(f'{path} 가 없다. py src/make_data/gen_seed.py 를 먼저 돌린다.')

    with path.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)

    # --- 헤더 검증 ---
    # 옛 load_db.py 에 이 검사를 넣은 이유가 그대로 유효하다. pet_purchases.csv 가
    # 10 -> 17 컬럼으로 갱신됐을 때 로더가 에러 없이 조용히 깨진 이력이 있다.
    cols = columns_of(con, table)
    unknown = [c for c in header if c not in cols]
    if unknown:
        raise ValueError(f'{path.name}: {table} 에 없는 컬럼 {unknown}')
    missing = [c for c, (notnull, has_default) in cols.items()
               if c not in header and notnull and not has_default]
    if missing:
        raise ValueError(f'{path.name}: NOT NULL 인데 CSV 에 없는 컬럼 {missing}')

    # 자기참조 테이블은 행 순서도 맞춰야 한다. 테이블 순서만으로는 부족하다.
    fk = self_fk_column(con, table)
    if fk:
        pk = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")') if r[5]][0]
        rows = order_rows_parents_first(rows, pk, fk)

    # INSERT 문은 CSV 헤더에서 만든다. 컬럼 목록을 코드에 또 적지 않는다 —
    # 적으면 스키마가 바뀔 때 세 군데(DDL / CSV / 여기)를 맞춰야 한다.
    sql = (f'INSERT INTO "{table}" ({", ".join(header)}) '
           f'VALUES ({", ".join("?" * len(header))})')
    # 빈 칸 -> NULL 이 유일한 변환이다. 숫자 캐스팅은 STRICT 가 이미 한다.
    con.executemany(sql, [[r[c] if r[c] != '' else None for c in header] for r in rows])

    omitted = [c for c in cols if c not in header]
    note = f'   (기본값에 맡긴 컬럼: {", ".join(omitted)})' if omitted else ''
    print(f'  {table:30} {len(rows):>6}행{note}')
    return len(rows)


def verify(con):
    """적재 후 검사. 여기를 통과해야 데이터가 쓸 수 있는 상태다."""
    broken = con.execute('PRAGMA foreign_key_check').fetchall()
    if broken:
        raise RuntimeError(f'FK 위반 {len(broken)}건: {broken[:5]}')
    print('\nFK 위반 0건')

    # 판정 3분법이 세 값 다 나오는가. 한 종류로 쏠려 있으면 이 데이터로는
    # 알러지 배제 로직을 시험할 수 없다 — 스키마는 멀쩡한데 검증만 헛돈다.
    verdicts = dict(con.execute(
        'SELECT verdict, count(*) FROM v_product_safety GROUP BY verdict').fetchall())
    print('v_product_safety 전체: '
          + ' / '.join(f'{v} {verdicts.get(v, 0)}쌍' for v in ('Safe', 'None', 'WARN')))
    if len(verdicts) < 3:
        print(f'[경고] verdict 가 {len(verdicts)}종류뿐이다. 3분법을 시험할 수 없는 데이터다.')

    # 특정 펫 하나를 걸고 쓰는 것이 이 뷰의 정상 사용법이다(WORK.md 2026-08-24).
    # 필터 없이 돌리면 56초, pet_id 를 걸면 6ms 였다.
    (starved,) = con.execute('''
        SELECT count(*) FROM pets pt
         WHERE pt.inactive_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM v_safe_products v WHERE v.pet_id = pt.pet_id)
    ''').fetchone()
    (active,) = con.execute('SELECT count(*) FROM pets WHERE inactive_at IS NULL').fetchone()
    print(f'활성 펫 {active}마리 중 Safe 후보 0개인 펫 {starved}마리')
    if starved > active * 0.1:
        print('[경고] 후보가 비는 펫이 너무 많다. 알러지를 상위 노드로 너무 자주 고르고 있다.')


def main():
    keep = '--keep' in sys.argv

    if keep:
        print(f'기존 스키마 유지: {DB_PATH.name}')
    else:
        print(f'스키마 재생성: {DB_PATH.name}')
        create_schema(str(DB_PATH), verbose=False)

    con = sqlite3.connect(DB_PATH)
    try:
        con.execute('PRAGMA foreign_keys = ON')

        # 무엇을 먼저 넣어야 하는지 DB 에게 물어서 정한다.
        order = resolve_order(con, SOURCES)
        print_order(con, order)

        print('\n[적재]')
        total = 0
        # 전부 한 트랜잭션이다. 중간에 터지면 아무것도 안 들어간 상태로 남는다.
        with con:
            for table in order:
                total += load_table(con, table, SOURCES[table])
        print(f'  {"합계":30} {total:>6}행')
        verify(con)
    finally:
        con.close()


if __name__ == '__main__':
    main()
