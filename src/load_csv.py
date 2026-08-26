# Last Updated: 2026-08-25
"""
data/master + data/seed 의 CSV 를 user.db(16테이블 스키마)로 적재한다.

    data/master/*.csv ┐
                      ├─> load_csv.py ─> user.db
    data/seed/*.csv   ┘

옛 src/load_db.py 를 대체한다. 그쪽은 4테이블 비정규화 스키마 전용이고,
DDL 까지 스스로 만들었다. 여기서는 DDL 을 만들지 않는다 — 스키마의 단일 원천은
src/create_schema/ 이고, 이 파일은 그것이 만든 테이블에 값을 넣기만 한다.

적재 순서가 곧 FK 순서다. ORDER 를 바꾸면 부모가 없는 행이 들어가려다 IntegrityError 로 멈춘다.

    allergens -> breeds -> ingredients -> ingredient_allergens
      -> users -> pets -> pet_breeds -> pet_allergies
      -> products -> product_animal_categories / _nutrition / _feeding_purposes / _ingredients

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

# (테이블, CSV 경로). 순서가 곧 적재 순서다.
ORDER = [
    # --- 마스터: 사람이 채운다. 재생성하지 않는다 ---
    ('allergens', MASTER_DIR / 'allergens.csv'),
    ('breeds', MASTER_DIR / 'breeds.csv'),
    ('ingredients', MASTER_DIR / 'ingredients.csv'),
    ('ingredient_allergens', MASTER_DIR / 'ingredient_allergens.csv'),
    # --- 합성: gen_seed.py 가 시드 고정으로 뽑는다 ---
    ('users', SEED_DIR / 'users.csv'),
    ('pets', SEED_DIR / 'pets.csv'),
    ('pet_breeds', SEED_DIR / 'pet_breeds.csv'),
    ('pet_allergies', SEED_DIR / 'pet_allergies.csv'),
    ('products', SEED_DIR / 'products.csv'),
    ('product_animal_categories', SEED_DIR / 'product_animal_categories.csv'),
    ('product_nutrition', SEED_DIR / 'product_nutrition.csv'),
    ('product_feeding_purposes', SEED_DIR / 'product_feeding_purposes.csv'),
    ('product_ingredients', SEED_DIR / 'product_ingredients.csv'),
]

# animal_categories / product_categories / feeding_purposes 는 여기에 없다.
# 코드(*_schema.py 의 SEEDS)가 넣는다. CSV 로 또 빼면 같은 값이 두 군데에 앉는다.


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


def order_parents_first(rows, pk, fk):
    """자기참조 테이블을 부모부터 나오도록 정렬한다.

    allergens 는 parent_id 로 자기를 가리키고 FK 검증이 켜져 있으므로,
    자식이 먼저 INSERT 되면 그 자리에서 터진다. CSV 를 손으로 편집하다가
    행 순서가 바뀌는 것은 흔한 일이라 파일 순서에 의존하지 않는다.
    """
    remaining = list(rows)
    done, out = set(), []
    while remaining:
        ready = [r for r in remaining if not r[fk] or r[fk] in done]
        if not ready:
            stuck = ', '.join(r[pk] for r in remaining[:5])
            raise RuntimeError(f'{fk} 가 순환하거나 없는 부모를 가리킨다: {stuck} ...')
        for r in ready:
            done.add(r[pk])
        out.extend(ready)
        remaining = [r for r in remaining if r not in ready]
    return out


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

    fk = self_fk_column(con, table)
    if fk:
        pk = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")') if r[5]][0]
        rows = order_parents_first(rows, pk, fk)

    sql = (f'INSERT INTO "{table}" ({", ".join(header)}) '
           f'VALUES ({", ".join("?" * len(header))})')
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
        print('\n[적재]')
        total = 0
        # 전부 한 트랜잭션이다. 중간에 터지면 아무것도 안 들어간 상태로 남는다.
        with con:
            for table, path in ORDER:
                total += load_table(con, table, path)
        print(f'  {"합계":30} {total:>6}행')
        verify(con)
    finally:
        con.close()


if __name__ == '__main__':
    main()
